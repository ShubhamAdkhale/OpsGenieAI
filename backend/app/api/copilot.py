"""Rule-based Copilot (§14 P2, §36 P2).

No LLM. Every answer is assembled from rows already in the database, which
keeps the §15 rule intact: the language layer never computes a risk score, it
only reads one that the deterministic engine produced.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DELIVERED, Machine, Product, Shipment, Workflow
from app.services import explain, forecasting, risk_engine
from app.services.formatting import inr

router = APIRouter(prefix="/copilot", tags=["copilot"])

SHIPMENT_CODE = re.compile(r"\bSC-\d{3,5}\b", re.IGNORECASE)
MACHINE_CODE = re.compile(r"\b(?:RF|CV|CM)-\d{3}\b", re.IGNORECASE)


def _answer_shipment(db: Session, shipment: Shipment) -> str:
    assessment = risk_engine.latest_assessment(db, shipment.id)
    result = risk_engine.optimize(shipment)
    lines = [
        f"{shipment.code} ({shipment.product.name}, {shipment.origin_city} to "
        f"{shipment.destination_city}) is {shipment.status} with a Melt Index of "
        f"{shipment.melt_index:.0f}.",
        f"Spoilage probability {shipment.spoilage_probability * 100:.0f}%, "
        f"expected loss {inr(shipment.expected_loss_inr)} of a "
        f"{inr(shipment.shipment_value_inr)} load.",
    ]
    if assessment is not None:
        lines.append("Drivers: " + "; ".join(explain.risk_bullets(assessment)) + ".")
    if result.should_reroute:
        lines.append(explain.explain_recommendation(shipment, result))
    return " ".join(lines)


def _answer_machine(db: Session, machine: Machine) -> str:
    from app.services import maintenance

    assessment = maintenance.assess(machine)
    detail = explain.explain_machine(machine, assessment)
    carried = [s.code for s in machine.active_shipments]
    tail = f" Currently assigned to {', '.join(carried)}." if carried else ""
    return detail["headline"] + " " + "; ".join(detail["bullets"]) + "." + tail


@router.get("/ask")
def ask(
    q: str = Query(..., min_length=2, max_length=300),
    db: Session = Depends(get_db),
) -> dict:
    question = q.strip()
    lowered = question.lower()
    sources: list[str] = []

    code_match = SHIPMENT_CODE.search(question)
    if code_match:
        shipment = (
            db.query(Shipment)
            .filter(Shipment.code == code_match.group(0).upper())
            .one_or_none()
        )
        if shipment is not None:
            return {
                "question": question,
                "answer": _answer_shipment(db, shipment),
                "sources": ["shipments", "risk_assessments", "routes"],
                "engine": "rule-based",
            }

    machine_match = MACHINE_CODE.search(question)
    if machine_match:
        machine = (
            db.query(Machine)
            .filter(Machine.code == machine_match.group(0).upper())
            .one_or_none()
        )
        if machine is not None:
            return {
                "question": question,
                "answer": _answer_machine(db, machine),
                "sources": ["machines", "sensor_readings"],
                "engine": "rule-based",
            }

    if any(word in lowered for word in ("riskiest", "worst", "at risk", "critical", "risk")):
        shipments = (
            db.query(Shipment)
            .filter(Shipment.status.notin_(["REROUTED", DELIVERED]))
            .order_by(Shipment.melt_index.desc())
            .limit(3)
            .all()
        )
        if shipments:
            listed = "; ".join(
                f"{s.code} at Melt Index {s.melt_index:.0f} ({s.status}), "
                f"{inr(s.expected_loss_inr)} expected loss"
                for s in shipments
            )
            return {
                "question": question,
                "answer": f"Highest-risk active shipments right now: {listed}.",
                "sources": ["shipments"],
                "engine": "rule-based",
            }

    if any(word in lowered for word in ("stock", "inventory", "reorder", "forecast", "demand")):
        results = [
            forecasting.forecast_product(db, p).to_payload()
            for p in db.query(Product).order_by(Product.id).all()
        ]
        flagged = [r for r in results if r["recommended_reorder_qty"] > 0]
        if flagged:
            listed = "; ".join(
                f"{r['product_name']}: {r['predicted_demand']:.0f} units forecast over the next "
                f"{forecasting.HORIZON_DAYS} days vs {r['current_stock']:.0f} in stock, "
                f"reorder {r['recommended_reorder_qty']:.0f}"
                for r in flagged
            )
            return {
                "question": question,
                "answer": f"Products needing a reorder: {listed}.",
                "sources": ["forecasts", "inventory", "demand_history"],
                "engine": "rule-based",
            }
        return {
            "question": question,
            "answer": "No product is forecast to run short over the next "
            f"{forecasting.HORIZON_DAYS} days.",
            "sources": ["forecasts", "inventory"],
            "engine": "rule-based",
        }

    if any(word in lowered for word in ("workflow", "approve", "pending", "approval")):
        pending = (
            db.query(Workflow)
            .filter(Workflow.status == "PENDING_APPROVAL")
            .order_by(Workflow.impact_inr.desc())
            .all()
        )
        if pending:
            listed = "; ".join(
                f"#{w.id} {w.workflow_type} ({inr(w.impact_inr)} impact, "
                f"{w.confidence} confidence)"
                for w in pending
            )
            return {
                "question": question,
                "answer": f"{len(pending)} workflow(s) waiting on your approval: {listed}.",
                "sources": ["workflows"],
                "engine": "rule-based",
            }
        return {
            "question": question,
            "answer": "Nothing is waiting on approval.",
            "sources": ["workflows"],
            "engine": "rule-based",
        }

    del sources
    return {
        "question": question,
        "answer": (
            "I answer from the operational database only. Try naming a shipment "
            "(e.g. 'SC-1042'), a machine ('RF-204'), or asking about risk, "
            "inventory, or pending approvals."
        ),
        "sources": [],
        "engine": "rule-based",
    }
