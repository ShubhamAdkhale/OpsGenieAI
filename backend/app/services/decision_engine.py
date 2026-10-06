"""Confidence-gated decision engine and workflow automation (§21 §22 §23).

The rule table from §21 lives here as constants. The most important property it
guarantees is a SAFETY property, not a UX one: no HIGH-impact action is ever
auto-executed without a logged human approval (§34).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Machine, Route, Shipment, Workflow
from app.services import risk_engine
from app.simulation import clock
from app.services.alerts import raise_alert
from app.services.explain import explain_recommendation, runway_sentence
from app.services.formatting import inr
from app.services.maintenance import FAILURE_PROBABILITY_ALERT_THRESHOLD

# --- §21 rule table constants -------------------------------------------------
CONFIDENCE_HIGH = 0.70
CONFIDENCE_LOW = 0.40
IMPACT_LOW_CEILING = 25_000.0
IMPACT_MEDIUM_CEILING = 100_000.0

AUTO_EXECUTED = "AUTO_EXECUTED"
PENDING_APPROVAL = "PENDING_APPROVAL"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
EXECUTED = "EXECUTED"
OVERRIDDEN = "OVERRIDDEN"
# Closed by events, not by a person: the load was delivered before anyone
# decided. Kept on the record rather than deleted, like every resolution.
EXPIRED = "EXPIRED"

OPEN_STATUSES = {PENDING_APPROVAL}

# A reroute is a PHYSICAL action: a driver changes lane, a cold hub accepts a
# transfer, a delivery slot moves. It is not worth doing for a rounding error.
#
# This floor exists because the optimizer is now fed a continuously changing
# world rather than three scripted steps, and it will always find *some*
# marginally better lane. Without a materiality test the engine would propose
# sub-1% improvements every tick, and the auto-execute row of the rule table
# would quietly act on them - a shipment could reroute itself before anyone had
# looked at the dashboard. A saving has to clear BOTH an absolute floor and a
# share of what is being protected before it counts as a decision.
REROUTE_MIN_SAVING_INR = 15_000.0
REROUTE_MIN_SAVING_FRACTION = 0.05

# A failing reefer needs a part as well as a technician. Deliberately priced
# below IMPACT_LOW_CEILING with high confidence, so it demonstrates the one
# §21 row that actually auto-executes.
SPARE_PART_COST_INR = 18_000.0
SPARE_PART_CONFIDENCE = 0.85


def utcnow() -> datetime:
    """Twin time - a decision is stamped with the moment it happened in the twin."""
    return clock.now()


def classify_confidence(score: float) -> str:
    if score >= CONFIDENCE_HIGH:
        return "HIGH"
    if score < CONFIDENCE_LOW:
        return "LOW"
    return "MEDIUM"


def classify_impact(impact_inr: float) -> str:
    if impact_inr < IMPACT_LOW_CEILING:
        return "LOW"
    if impact_inr <= IMPACT_MEDIUM_CEILING:
        return "MEDIUM"
    return "HIGH"


def reroute_is_material(shipment: Shipment, loss_avoided_inr: float) -> bool:
    """Is this saving big enough to be worth physically moving a truck?"""
    threshold = max(
        REROUTE_MIN_SAVING_INR,
        REROUTE_MIN_SAVING_FRACTION * float(shipment.shipment_value_inr),
    )
    return float(loss_avoided_inr) >= threshold


@dataclass
class Decision:
    confidence: str
    confidence_score: float
    impact_band: str
    impact_inr: float
    status: str
    rationale: str


def decide(confidence_score: float, impact_inr: float) -> Decision:
    """The §21 table, evaluated in the order the table implies.

    LOW confidence is checked first because it overrides the auto-execute row —
    a low-confidence recommendation is never auto-executed regardless of how
    small the impact is.
    """
    confidence = classify_confidence(confidence_score)
    impact_band = classify_impact(impact_inr)

    if confidence == "LOW":
        status = PENDING_APPROVAL
        rationale = (
            "Low model confidence — recommendation only, human approval required "
            "before any action."
        )
    elif impact_band == "HIGH":
        status = PENDING_APPROVAL
        rationale = (
            f"Impact of {inr(impact_inr)} exceeds the "
            f"{inr(IMPACT_MEDIUM_CEILING)} auto-execution ceiling — mandatory "
            "human approval regardless of confidence."
        )
    elif impact_band == "MEDIUM":
        status = PENDING_APPROVAL
        rationale = (
            f"Medium impact ({inr(impact_inr)}) — recommended and queued for "
            "one-click approval."
        )
    elif confidence == "HIGH":
        status = AUTO_EXECUTED
        rationale = (
            f"High confidence ({confidence_score:.2f}) and low impact "
            f"({inr(impact_inr)}) — auto-executed and logged."
        )
    else:
        status = PENDING_APPROVAL
        rationale = (
            f"Medium confidence ({confidence_score:.2f}) — queued for approval "
            "rather than auto-executed."
        )

    return Decision(
        confidence=confidence,
        confidence_score=round(confidence_score, 4),
        impact_band=impact_band,
        impact_inr=impact_inr,
        status=status,
        rationale=rationale,
    )


def confidence_from_probabilities(current_p: float, recommended_p: float) -> float:
    """§21 defines confidence as the model's probability margin from 0.5.

    We take the larger margin of the two probabilities being compared: a
    decision built on a 0.82 vs 0.21 comparison is better supported than one
    built on 0.51 vs 0.49.
    """
    return max(abs(current_p - 0.5), abs(recommended_p - 0.5)) * 2.0


# ---------------------------------------------------------------------------
# Reroute evaluation
# ---------------------------------------------------------------------------


def open_workflow(
    db: Session, workflow_type: str, shipment_id: int | None = None, machine_id: int | None = None
) -> Workflow | None:
    query = db.query(Workflow).filter(
        Workflow.workflow_type == workflow_type, Workflow.status.in_(OPEN_STATUSES)
    )
    if shipment_id is not None:
        query = query.filter(Workflow.related_shipment_id == shipment_id)
    if machine_id is not None:
        query = query.filter(Workflow.related_machine_id == machine_id)
    return query.order_by(Workflow.id.desc()).first()


def evaluate_shipment(
    db: Session, shipment: Shipment, allow_auto_execute: bool = True
) -> Workflow | None:
    """Run the §20 optimizer, apply the §21 rules, create/refresh a REROUTE
    workflow. Called by every simulation trigger right after `recalculate`.

    `allow_auto_execute=False` downgrades an AUTO_EXECUTED verdict to
    PENDING_APPROVAL without touching the shipment. Seeding uses it: the
    baseline represents the moment the manager opens the dashboard, and a
    shipment silently rerouting itself during `seed()` would both hide the
    decision from the demo and rewrite the routes before anyone saw them.
    """
    result = risk_engine.optimize(shipment)
    if not result.should_reroute:
        return None
    if not reroute_is_material(shipment, result.loss_avoided_inr):
        return None

    confidence_score = confidence_from_probabilities(
        result.current.spoilage_probability, result.recommended.spoilage_probability
    )
    decision = decide(confidence_score, result.loss_avoided_inr)
    if decision.status == AUTO_EXECUTED and not allow_auto_execute:
        decision.status = PENDING_APPROVAL
        decision.rationale = (
            f"{decision.rationale} Held for approval instead of auto-executing "
            "because this decision was produced while seeding the baseline."
        )
    recommendation = explain_recommendation(shipment, result)

    existing = open_workflow(db, "REROUTE", shipment_id=shipment.id)
    workflow = existing or Workflow(
        workflow_type="REROUTE",
        related_shipment_id=shipment.id,
        related_machine_id=shipment.machine_id,
        status=decision.status,
    )
    workflow.trigger_reason = (
        f"{shipment.code} Melt Index {shipment.melt_index:.0f} "
        f"({shipment.status}); expected loss {inr(result.current.expected_loss_inr)} "
        f"on {result.current.route.label}"
    )
    workflow.confidence = decision.confidence
    workflow.confidence_score = decision.confidence_score
    workflow.impact_inr = result.loss_avoided_inr
    workflow.recommendation_text = recommendation
    workflow.proposed_route_id = result.recommended.route.id
    workflow.resolution_note = decision.rationale
    if existing is None:
        workflow.status = decision.status
        db.add(workflow)
    db.flush()

    if workflow.status == AUTO_EXECUTED:
        _execute_reroute(db, shipment, result.recommended.route, result.loss_avoided_inr)
        workflow.executed_route_id = result.recommended.route.id
        workflow.resolved_at = utcnow()
        db.flush()

    severity = "CRITICAL" if shipment.status in {"HIGH", "CRITICAL"} else "WARNING"
    raise_alert(
        db,
        severity,
        f"{shipment.code}: Melt Index {shipment.melt_index:.0f} ({shipment.status}). "
        f"{inr(result.current.expected_loss_inr)} at risk. "
        f"Recommended: {result.recommended.route.label}.",
        related_type="shipment",
        related_id=shipment.id,
        # One alert per (shipment, risk band): a new one when the band changes,
        # refreshed in place while it holds.
        dedupe_key=f"shipment-risk:{shipment.code}:{shipment.status}",
    )
    return workflow


def evaluate_machine(db: Session, machine: Machine, assessment) -> Workflow | None:
    """§17: a unit crossing failure_probability > 0.75 raises a CRITICAL alert
    and auto-creates a maintenance workflow."""
    if assessment.insufficient_data:
        return None
    if assessment.failure_probability <= FAILURE_PROBABILITY_ALERT_THRESHOLD:
        return None

    raise_alert(
        db,
        "CRITICAL",
        f"{machine.code} ({machine.type.replace('_', ' ')}) at {machine.location}: "
        f"condition risk {assessment.failure_probability * 100:.0f}%, "
        f"health {machine.health_score:.0f}%. Maintenance required.",
        related_type="machine",
        related_id=machine.id,
        dedupe_key=f"machine-failure:{machine.code}:{machine.status}",
    )
    return create_maintenance_workflow(db, machine, assessment, auto=True)


def create_maintenance_workflow(
    db: Session, machine: Machine, assessment, auto: bool = False
) -> Workflow:
    existing = open_workflow(db, "MAINTENANCE", machine_id=machine.id)
    if existing is not None:
        return existing

    # Impact of a reefer failure = the value of whatever it is currently
    # carrying, which is exactly the cross-module link in §5.
    carried = [s for s in machine.active_shipments if s.status != "REROUTED"]
    impact = sum(float(s.shipment_value_inr) for s in carried)
    runway = runway_sentence(assessment.estimated_failure_hours)
    eta = f" {runway}." if runway else ""
    reason = (
        f"{machine.code} condition risk {assessment.failure_probability * 100:.0f}% "
        f"(health {machine.health_score:.0f}%)."
        + (
            f" Currently assigned to {', '.join(s.code for s in carried)}."
            if carried
            else " Not currently assigned to a shipment."
        )
    )
    decision = decide(assessment.failure_probability, impact)
    workflow = Workflow(
        workflow_type="MAINTENANCE",
        related_machine_id=machine.id,
        related_shipment_id=carried[0].id if carried else None,
        trigger_reason=reason,
        confidence=decision.confidence,
        confidence_score=decision.confidence_score,
        impact_inr=impact,
        status=PENDING_APPROVAL,
        recommendation_text=(
            f"Dispatch a technician to {machine.code} at {machine.location} and swap in "
            f"the standby unit before the next dispatch.{eta}"
        ),
        resolution_note=("Auto-created by the maintenance monitor." if auto else "Created manually."),
    )
    db.add(workflow)
    db.flush()

    # A failing reefer usually needs a part as well as a technician. Small,
    # high-confidence, low-impact -> exactly the §21 auto-execute row.
    part_decision = decide(SPARE_PART_CONFIDENCE, SPARE_PART_COST_INR)
    part = Workflow(
        workflow_type="SPARE_PART_PURCHASE",
        related_machine_id=machine.id,
        trigger_reason=f"{machine.code} maintenance workflow #{workflow.id} raised.",
        confidence=part_decision.confidence,
        confidence_score=part_decision.confidence_score,
        impact_inr=SPARE_PART_COST_INR,
        status=part_decision.status,
        recommendation_text=(
            f"Order a replacement compressor seal kit for {machine.code} "
            f"({inr(SPARE_PART_COST_INR)}, within the auto-approval ceiling)."
        ),
        resolution_note=part_decision.rationale,
        resolved_at=utcnow() if part_decision.status == AUTO_EXECUTED else None,
    )
    db.add(part)
    db.flush()
    if part.status == AUTO_EXECUTED:
        raise_alert(
            db,
            "INFO",
            f"Auto-executed: spare part ordered for {machine.code} "
            f"({inr(SPARE_PART_COST_INR)}), within the auto-approval ceiling.",
            related_type="machine",
            related_id=machine.id,
        )
    return workflow


# ---------------------------------------------------------------------------
# Execution (§22). Actions update the twin's own records; no courier, ERP or
# work-order system is called. That is stated once - the "Digital twin" badge,
# the footer and `simulated_execution` on every workflow payload - rather than
# repeated inside every alert, where it made the feed read as a test harness.
# ---------------------------------------------------------------------------


def _execute_reroute(db: Session, shipment: Shipment, route: Route, loss_avoided: float) -> None:
    for r in shipment.routes:
        r.is_selected = r.id == route.id
    shipment.loss_avoided_inr = loss_avoided
    shipment.status = "REROUTED"
    db.flush()
    risk_engine.recalculate(db, shipment)
    shipment.status = "REROUTED"
    raise_alert(
        db,
        "INFO",
        f"{shipment.code} rerouted to {route.label}. Risk mitigated — "
        f"{inr(loss_avoided)} of expected loss avoided.",
        related_type="shipment",
        related_id=shipment.id,
        dedupe=False,
    )


def execute_workflow(
    db: Session, workflow: Workflow, override_route_id: int | None = None
) -> Workflow:
    """Run the action behind an approved workflow.

    "Executing" here means updating the related rows and writing a log/alert.
    There is no real courier API and no real ERP in this build (§22), and the
    UI labels every execution as simulated.
    """
    if workflow.workflow_type == "REROUTE":
        shipment = db.get(Shipment, workflow.related_shipment_id)
        route_id = override_route_id or workflow.proposed_route_id
        route = db.get(Route, route_id) if route_id else None
        if shipment is None or route is None:
            workflow.status = REJECTED
            workflow.resolution_note = "Could not execute: shipment or route missing."
            workflow.resolved_at = utcnow()
            db.flush()
            return workflow

        result = risk_engine.optimize(shipment)
        chosen = next((e for e in result.evaluations if e.route.id == route.id), None)
        loss_avoided = 0.0
        if result.current is not None and chosen is not None:
            loss_avoided = max(0.0, result.current.expected_loss_inr - chosen.expected_loss_inr)

        _execute_reroute(db, shipment, route, loss_avoided)
        workflow.executed_route_id = route.id
        workflow.impact_inr = loss_avoided
        workflow.status = OVERRIDDEN if override_route_id else EXECUTED

    elif workflow.workflow_type == "MAINTENANCE":
        machine = db.get(Machine, workflow.related_machine_id)
        workflow.status = EXECUTED
        if machine is not None:
            raise_alert(
                db,
                "INFO",
                f"Maintenance dispatched for {machine.code} at {machine.location}.",
                related_type="machine",
                related_id=machine.id,
                dedupe=False,
            )
    else:
        workflow.status = EXECUTED
        raise_alert(
            db,
            "INFO",
            f"Workflow #{workflow.id} ({workflow.workflow_type.replace('_', ' ').lower()}) executed.",
            dedupe=False,
        )

    workflow.resolved_at = utcnow()
    db.flush()
    return workflow


def approve(db: Session, workflow: Workflow, override_route_id: int | None = None) -> Workflow:
    """§23: approvals are timestamped and never edited afterwards."""
    if workflow.status not in OPEN_STATUSES:
        return workflow
    workflow.status = APPROVED
    note = "Approved by ops manager."
    if override_route_id:
        note = f"Overridden by ops manager: route #{override_route_id} chosen instead of the AI recommendation."
    workflow.resolution_note = f"{workflow.resolution_note} | {note}".strip(" |")
    db.flush()
    return execute_workflow(db, workflow, override_route_id=override_route_id)


def reject(db: Session, workflow: Workflow, note: str = "") -> Workflow:
    if workflow.status not in OPEN_STATUSES:
        return workflow
    workflow.status = REJECTED
    workflow.resolved_at = utcnow()
    workflow.resolution_note = (
        f"{workflow.resolution_note} | Rejected by ops manager. {note}".strip(" |")
    )
    db.flush()
    raise_alert(
        db,
        "WARNING",
        f"Workflow #{workflow.id} ({workflow.workflow_type}) rejected by the ops manager. "
        "No action taken.",
        dedupe=False,
    )
    return workflow
