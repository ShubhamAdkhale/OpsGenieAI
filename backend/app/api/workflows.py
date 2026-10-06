from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.serializers import workflow_payload
from app.database import get_db
from app.models import Route, Shipment, Workflow
from app.schemas import ApproveRequest, RejectRequest
from app.services import decision_engine

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _get_workflow(db: Session, workflow_id: int) -> Workflow:
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    return workflow


@router.get("")
def list_workflows(db: Session = Depends(get_db)) -> list[dict]:
    workflows = db.query(Workflow).order_by(Workflow.id.desc()).all()
    return [workflow_payload(w) for w in workflows]


AUTOMATED = {"AUTO_EXECUTED"}
HUMAN_RESOLVED = {"EXECUTED", "OVERRIDDEN", "REJECTED"}


@router.get("/summary")
def workflow_summary(db: Session = Depends(get_db)) -> dict:
    """The business impact of the decision layer, for the Workflows page header.

    Declared before `/{workflow_id}` so "summary" is never parsed as an id.
    Loss avoided is read off the shipments (what reroutes actually saved), not
    summed from workflow impact estimates, which are forecasts.
    """
    workflows = db.query(Workflow).all()
    resolved = [w for w in workflows if w.status in AUTOMATED | HUMAN_RESOLVED]
    automated = [w for w in resolved if w.status in AUTOMATED]
    pending = [w for w in workflows if w.status == "PENDING_APPROVAL"]

    waits = sorted(
        (w.resolved_at - w.created_at).total_seconds()
        for w in workflows
        if w.status in HUMAN_RESOLVED and w.resolved_at and w.created_at
    )
    median_wait = waits[len(waits) // 2] if waits else None

    return {
        "total": len(workflows),
        "loss_avoided_inr": round(sum(float(s.loss_avoided_inr) for s in db.query(Shipment).all())),
        "automation_rate": round(len(automated) / len(resolved), 3) if resolved else None,
        "auto_executed": len(automated),
        "human_resolved": len(resolved) - len(automated),
        "pending": len(pending),
        "pending_impact_inr": round(sum(float(w.impact_inr) for w in pending)),
        "median_seconds_to_human_decision": median_wait,
        "by_type": {
            kind: sum(1 for w in workflows if w.workflow_type == kind)
            for kind in sorted({w.workflow_type for w in workflows})
        },
    }


@router.get("/{workflow_id}")
def get_workflow(workflow_id: int, db: Session = Depends(get_db)) -> dict:
    return workflow_payload(_get_workflow(db, workflow_id))


@router.post("/{workflow_id}/approve")
def approve_workflow(
    workflow_id: int, payload: ApproveRequest, db: Session = Depends(get_db)
) -> dict:
    """§23: approve (or override) a pending workflow and execute the action."""
    workflow = _get_workflow(db, workflow_id)
    if not workflow.requires_approval_now():
        raise HTTPException(
            status_code=409,
            detail=(
                f"Workflow {workflow_id} is {workflow.status} — only PENDING_APPROVAL "
                "workflows can be approved. Approvals are immutable (§23)."
            ),
        )
    if payload.override_route_id is not None:
        route = db.get(Route, payload.override_route_id)
        if route is None or route.shipment_id != workflow.related_shipment_id:
            raise HTTPException(
                status_code=400,
                detail="override_route_id must be a route on this workflow's shipment",
            )
    decision_engine.approve(db, workflow, override_route_id=payload.override_route_id)
    db.commit()
    return workflow_payload(workflow)


@router.post("/{workflow_id}/reject")
def reject_workflow(
    workflow_id: int, payload: RejectRequest, db: Session = Depends(get_db)
) -> dict:
    workflow = _get_workflow(db, workflow_id)
    if not workflow.requires_approval_now():
        raise HTTPException(
            status_code=409,
            detail=f"Workflow {workflow_id} is already {workflow.status}.",
        )
    decision_engine.reject(db, workflow, note=payload.note)
    db.commit()
    return workflow_payload(workflow)
