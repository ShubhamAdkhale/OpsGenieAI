"""The AI Priority Summary - one decision, chosen and worded in the backend.

The dashboard's first screen has to answer five questions in about ten seconds:

    WHAT is wrong?   WHAT will happen?   WHY?   WHAT should I do?   HOW MUCH is at risk?

Those answers are assembled here rather than in React, for the same reason the
Melt Index is: the browser must not be a second place where business logic
lives. The frontend renders `answers` and `financial` verbatim - it does no
ranking, no thresholding and no arithmetic on rupees.

Ranking rule: the top item is the one with the largest EXPECTED LOSS still on
the table, because that is the decision whose delay costs the most. Equipment
that threatens a shipment is folded into that shipment's causes rather than
competing with it for the top slot, so the manager sees one problem with a
reason, not two cards to correlate by hand.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import DELIVERED, Machine, Shipment, Workflow
from app.services import explain, maintenance, risk_engine
from app.services.formatting import inr

# Below this the board is calm and the summary says so rather than inventing a
# crisis out of the highest of several harmless numbers.
ATTENTION_EXPECTED_LOSS_INR = 40_000.0

SEVERITY_FOR_STATUS = {
    "CRITICAL": "CRITICAL",
    "HIGH": "HIGH",
    "MODERATE": "MODERATE",
    "LOW": "LOW",
    "SAFE": "NORMAL",
    "REROUTED": "NORMAL",
}


def _percent(value: float) -> str:
    return f"{float(value) * 100:.0f}%"


def _machine_context(db: Session, machine: Machine | None) -> dict | None:
    """The equipment story behind a shipment's risk, if there is one."""
    if machine is None:
        return None
    assessment = maintenance.assess(machine)
    if machine.status == "HEALTHY" and not machine.anomaly_detected:
        return None
    return {
        "id": machine.id,
        "code": machine.code,
        "status": machine.status,
        "health_score": round(machine.health_score, 1),
        "cooling_efficiency": round(machine.cooling_efficiency, 1),
        "efficiency_drop": round(
            max(0.0, machine.baseline_cooling_efficiency - machine.cooling_efficiency), 1
        ),
        "failure_probability": machine.failure_probability,
        "anomaly_detected": machine.anomaly_detected,
        "estimated_failure_hours": machine.estimated_failure_hours,
        "top_risk_factors": assessment.top_risk_factors[:2],
    }


def _causes(db: Session, shipment: Shipment) -> list[dict]:
    """The weighted components actually driving this shipment's score.

    Reuses the same contribution breakdown the explainability panel shows, so
    the summary's "main causes" line and the detail page can never disagree.
    """
    assessment = risk_engine.latest_assessment(db, shipment.id)
    if assessment is None:
        return []
    payload = explain.explain_risk(shipment, assessment)
    contributions = sorted(
        payload.get("contributions", []), key=lambda c: c.get("points", 0.0), reverse=True
    )
    return [c for c in contributions if c.get("points", 0.0) >= 4.0][:3]


def _pending_reroute(db: Session, shipment: Shipment) -> Workflow | None:
    return (
        db.query(Workflow)
        .filter(
            Workflow.related_shipment_id == shipment.id,
            Workflow.workflow_type == "REROUTE",
            Workflow.status == "PENDING_APPROVAL",
        )
        .order_by(Workflow.id.desc())
        .first()
    )


def _headline(code: str, probability: float, expected_loss: float) -> str:
    """Say only as much as the probability on the same card supports.

    The card used to open "SC-1042 is predicted to spoil before delivery" at a
    19% spoilage probability. "Predicted to spoil" is a claim about the likely
    outcome, so it is reserved for the likely case; below that the headline
    leads with the money, which is why the load is on top at all.
    """
    if probability >= 0.5:
        return f"{code} is predicted to spoil before delivery."
    if probability >= 0.25:
        return f"{code} is at serious risk of spoiling before delivery."
    return f"{code} carries {inr(expected_loss)} of expected spoilage loss."


def summarize(db: Session) -> dict:
    """The single most important decision on the board right now."""
    active = [
        s for s in db.query(Shipment).all() if s.status not in ("REROUTED", DELIVERED)
    ]
    if not active:
        return _calm(db, "No active shipments in transit.")

    subject = max(active, key=lambda s: float(s.expected_loss_inr))
    if float(subject.expected_loss_inr) < ATTENTION_EXPECTED_LOSS_INR:
        # A rerouted load has already been decided, so it is not "the next
        # decision" - but it can still be at risk, and a calm card must not
        # read as though it were safe.
        rerouted_at_risk = (
            db.query(Shipment)
            .filter(Shipment.status == "REROUTED", Shipment.melt_index > 40)
            .count()
        )
        tail = (
            f" {rerouted_at_risk} already-rerouted shipment(s) are still at elevated "
            "risk and being monitored."
            if rerouted_at_risk
            else ""
        )
        return _calm(
            db,
            f"All {len(active)} shipments awaiting a decision are inside their safe envelope. "
            f"Highest single exposure is {inr(subject.expected_loss_inr)}.{tail}",
        )

    optimization = risk_engine.optimize(subject)
    causes = _causes(db, subject)
    machine = _machine_context(db, subject.machine)
    workflow = _pending_reroute(db, subject)

    recommended = optimization.recommended
    current = optimization.current
    loss_avoided = optimization.loss_avoided_inr
    can_act = (
        recommended is not None
        and current is not None
        and optimization.should_reroute
        and loss_avoided > 0
    )

    cause_phrase = " + ".join(c["component"] for c in causes) if causes else "multiple factors"

    # WHAT should I do?
    if workflow is not None:
        action = {
            "type": workflow.workflow_type,
            "text": workflow.recommendation_text,
            "workflow_id": workflow.id,
            "status": workflow.status,
            "confidence": workflow.confidence,
            "confidence_score": workflow.confidence_score,
            "requires_approval": True,
            "gate_reason": workflow.resolution_note,
            "proposed_route_id": workflow.proposed_route_id,
        }
        what_to_do = workflow.recommendation_text
    elif can_act:
        action = {
            "type": "REROUTE",
            "text": explain.explain_recommendation(subject, optimization),
            "workflow_id": None,
            "status": "MONITORING",
            "confidence": None,
            "confidence_score": None,
            "requires_approval": False,
            "gate_reason": (
                "Modelled saving is below the materiality floor, so no reroute has "
                "been raised. Being monitored every tick."
            ),
            "proposed_route_id": recommended.route.id,
        }
        what_to_do = action["text"]
    elif optimization.no_safe_option:
        action = {
            "type": "ESCALATE",
            "text": (
                f"No lane arrives inside {subject.code}'s remaining shelf life. "
                "Escalate for a partial write-off or a local diversion."
            ),
            "workflow_id": None,
            "status": "ESCALATION",
            "confidence": None,
            "confidence_score": None,
            "requires_approval": True,
            "gate_reason": "Every candidate route misses the shelf-life window.",
            "proposed_route_id": None,
        }
        what_to_do = action["text"]
    else:
        action = {
            "type": "MONITOR",
            "text": f"Hold {subject.code} on its current lane and keep watching.",
            "workflow_id": None,
            "status": "MONITORING",
            "confidence": None,
            "confidence_score": None,
            "requires_approval": False,
            "gate_reason": "No alternative lane reduces expected loss.",
            "proposed_route_id": None,
        }
        what_to_do = action["text"]

    severity = SEVERITY_FOR_STATUS.get(subject.status, "MODERATE")
    value = float(subject.shipment_value_inr)

    # Take the probability, the expected loss and the score from ONE evaluation.
    #
    # The columns on the shipment row are written by the physics tick, while
    # `optimize()` re-evaluates against the state as it stands this instant. In
    # a world that moves every few seconds those two disagree, and mixing them
    # produced a card that said "Rs 2,01,000 at risk" directly above "expected
    # loss falls from Rs 95,000". Both numbers were correct; reading them
    # together was not. The card now quotes the live evaluation throughout, and
    # the stored columns stay what they are - the per-tick audit record.
    if current is not None:
        probability = float(current.spoilage_probability)
        expected = float(current.expected_loss_inr)
        melt_index = round(current.components.melt_index)
    else:
        probability = float(subject.spoilage_probability)
        expected = float(subject.expected_loss_inr)
        melt_index = round(subject.melt_index)

    return {
        "state": "ATTENTION",
        "severity": severity,
        "headline": _headline(subject.code, probability, expected),
        "subject": {
            "type": "shipment",
            "id": subject.id,
            "code": subject.code,
            "product": subject.product.name if subject.product else None,
            "lane": f"{subject.origin_city} to {subject.destination_city}",
            "status": subject.status,
            "melt_index": melt_index,
            "cargo_temperature_c": subject.cargo_temperature_c,
            "safe_transit_temp_c": (
                subject.product.safe_transit_temp_c if subject.product else None
            ),
            "remaining_shelf_life_hours": round(subject.remaining_shelf_life_hours, 1),
        },
        # WHAT will happen?
        "prediction": {
            "label": "Spoilage probability",
            "probability": round(probability, 4),
            "probability_display": _percent(probability),
            "horizon": "before scheduled delivery",
        },
        # HOW MUCH is at risk?
        "financial": {
            "shipment_value_inr": value,
            "expected_loss_inr": expected,
            "loss_avoided_inr": loss_avoided if can_act else 0.0,
            "residual_loss_inr": (
                recommended.expected_loss_inr if can_act and recommended else expected
            ),
            # The arithmetic spelled out, because "why does this matter" is
            # answered by showing the multiplication, not by asserting a total.
            "working": (
                f"{inr(value)} x {_percent(probability)} = {inr(expected)}"
            ),
        },
        # WHY?
        "causes": causes,
        "cause_summary": cause_phrase,
        "equipment": machine,
        # WHAT should I do?
        "recommendation": action,
        "answers": {
            "what_is_wrong": (
                f"{subject.code} ({subject.product.name if subject.product else 'cargo'}) "
                f"on {subject.origin_city} to {subject.destination_city} is at "
                f"Melt Index {melt_index} ({subject.status})."
            ),
            "what_will_happen": (
                f"{_percent(probability)} probability of spoilage "
                "before delivery on the current lane."
            ),
            "why": cause_phrase,
            "what_to_do": what_to_do,
            "how_much_at_risk": (
                f"{inr(expected)} expected loss"
                + (f", {inr(loss_avoided)} recoverable" if can_act and loss_avoided else "")
                + "."
            ),
        },
        "disclaimer": (
            "Estimates from a simulated operational model, not a guarantee. "
            "Rupee figures are decision support."
        ),
    }


def _calm(db: Session, detail: str) -> dict:
    """The honest empty state. A control tower with nothing wrong should say so."""
    machines_at_risk = (
        db.query(Machine).filter(Machine.status.in_(["WARNING", "CRITICAL"])).count()
    )
    return {
        "state": "NORMAL",
        "severity": "NORMAL",
        "headline": "No shipment needs a decision right now.",
        "subject": None,
        "prediction": None,
        "financial": None,
        "causes": [],
        "cause_summary": "",
        "equipment": None,
        "recommendation": {
            "type": "NONE",
            "text": (
                f"{machines_at_risk} unit(s) are being watched for degradation."
                if machines_at_risk
                else "Nothing requires action."
            ),
            "workflow_id": None,
            "status": "MONITORING",
            "confidence": None,
            "confidence_score": None,
            "requires_approval": False,
            "gate_reason": "",
            "proposed_route_id": None,
        },
        "answers": {
            "what_is_wrong": "Nothing above the attention threshold.",
            "what_will_happen": detail,
            "why": "",
            "what_to_do": "Monitor.",
            "how_much_at_risk": "",
        },
        "disclaimer": "Estimates from a simulated operational model.",
    }
