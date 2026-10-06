from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.serializers import (
    assessment_payload,
    shipment_detail,
    shipment_summary,
    workflow_payload,
)
from app.database import get_db
from app.models import Route, Shipment
from app.schemas import RerouteRequest
from app.services import decision_engine, explain, risk_engine

router = APIRouter(prefix="/shipments", tags=["shipments"])


def _get_shipment(db: Session, shipment_id: int) -> Shipment:
    shipment = db.get(Shipment, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=404, detail=f"Shipment {shipment_id} not found")
    return shipment


@router.get("")
def list_shipments(db: Session = Depends(get_db)) -> list[dict]:
    shipments = db.query(Shipment).order_by(Shipment.melt_index.desc()).all()
    return [shipment_summary(s) for s in shipments]


@router.get("/{shipment_id}")
def get_shipment(shipment_id: int, db: Session = Depends(get_db)) -> dict:
    return shipment_detail(db, _get_shipment(db, shipment_id))


@router.get("/{shipment_id}/risk")
def get_shipment_risk(shipment_id: int, db: Session = Depends(get_db)) -> dict:
    shipment = _get_shipment(db, shipment_id)
    assessment = risk_engine.latest_assessment(db, shipment.id)
    if assessment is None:
        assessment = risk_engine.recalculate(db, shipment)
        db.commit()
    return {
        "shipment_code": shipment.code,
        **assessment_payload(assessment),
        "explanation": explain.explain_risk(shipment, assessment),
    }


@router.get("/{shipment_id}/routes")
def get_shipment_routes(shipment_id: int, db: Session = Depends(get_db)) -> dict:
    shipment = _get_shipment(db, shipment_id)
    result = risk_engine.optimize(shipment)
    return {
        "shipment_code": shipment.code,
        "routes": [e.to_payload() for e in result.evaluations],
        "current_route_id": result.current.route.id if result.current else None,
        "recommended_route_id": result.recommended.route.id if result.recommended else None,
        "potential_loss_avoided_inr": result.loss_avoided_inr,
        "no_safe_option": result.no_safe_option,
        "recommendation_text": explain.explain_recommendation(shipment, result),
    }


@router.post("/{shipment_id}/reroute")
def reroute_shipment(
    shipment_id: int, payload: RerouteRequest, db: Session = Depends(get_db)
) -> dict:
    """Executes a reroute directly (§14). The route must belong to the shipment.

    This is the manual path; the normal demo path goes through
    POST /api/workflows/{id}/approve so the approval is auditable.
    """
    shipment = _get_shipment(db, shipment_id)
    route = db.get(Route, payload.route_id)
    if route is None or route.shipment_id != shipment.id:
        raise HTTPException(
            status_code=400,
            detail=f"Route {payload.route_id} does not belong to shipment {shipment.code}",
        )

    workflow = decision_engine.open_workflow(db, "REROUTE", shipment_id=shipment.id)
    if workflow is None:
        result = risk_engine.optimize(shipment)
        chosen = next((e for e in result.evaluations if e.route.id == route.id), None)
        loss_avoided = 0.0
        if result.current is not None and chosen is not None:
            loss_avoided = max(0.0, result.current.expected_loss_inr - chosen.expected_loss_inr)
        decision = decision_engine.decide(
            decision_engine.confidence_from_probabilities(
                result.current.spoilage_probability if result.current else 0.5,
                chosen.spoilage_probability if chosen else 0.5,
            ),
            loss_avoided,
        )
        from app.models import Workflow

        workflow = Workflow(
            workflow_type="REROUTE",
            related_shipment_id=shipment.id,
            related_machine_id=shipment.machine_id,
            trigger_reason=f"Manual reroute requested for {shipment.code}.",
            confidence=decision.confidence,
            confidence_score=decision.confidence_score,
            impact_inr=loss_avoided,
            status="PENDING_APPROVAL",
            recommendation_text=f"Manual reroute of {shipment.code} to {route.label}.",
            proposed_route_id=route.id,
            resolution_note="Created by a direct reroute request.",
        )
        db.add(workflow)
        db.flush()

    override = None if workflow.proposed_route_id == route.id else route.id
    decision_engine.approve(db, workflow, override_route_id=override)
    db.commit()
    db.refresh(shipment)
    return {
        "shipment": shipment_summary(shipment),
        "workflow": workflow_payload(workflow),
    }
