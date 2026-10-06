"""Rule-based explanations (§24).

Deliberately string templating, not an LLM and not NLP. When a judge asks "how
did you generate that sentence?", the answer is "we substituted the stored
RiskAssessment numbers into a fixed template" — 100% consistent, 100%
reproducible, and it cannot hallucinate a reason that the score did not have.
"""

from __future__ import annotations

from app.models import RiskAssessment, Shipment
from app.services.formatting import inr
from app.services.risk_engine import WEIGHTS, OptimizationResult, band_for

# A component earns a bullet only once it is actually pushing the score around.
THRESHOLDS = {
    "temperature": 12.0,
    "refrigeration": 12.0,
    "traffic": 12.0,
    "weather": 10.0,
    "shelf_life": 25.0,
    "eta": 25.0,
}

WEATHER_PHRASE = {
    "CLEAR": "clear",
    "RAIN": "rain",
    "STORM": "storm conditions",
    "EXTREME": "extreme weather",
}


def _minutes(value: float) -> str:
    return f"{value:.0f} minute{'s' if abs(value) >= 2 else ''}"


def _hours(value: float) -> str:
    return f"{value:.1f} hour{'s' if abs(value) >= 2 else ''}"


def runway_sentence(hours: float | None) -> str | None:
    """How long until cooling efficiency hits the floor, in words an operator uses.

    None when there is nothing useful to say: no decline, or a runway so long
    (the 30-day cap) that it is not a maintenance concern.
    """
    from app.services.maintenance import RUNWAY_CAP_HOURS

    if hours is None or hours >= RUNWAY_CAP_HOURS:
        return None
    if hours <= 0:
        return "Cooling efficiency is already below the critical floor"
    when = _hours(hours) if hours < 48 else f"{hours / 24:.0f} days"
    return f"At the current rate of decline, cooling efficiency reaches the critical floor in about {when}"


def risk_bullets(assessment: RiskAssessment) -> list[str]:
    """One templated sentence per risk component that crossed its threshold."""
    bullets: list[str] = []

    if assessment.temperature_risk >= THRESHOLDS["temperature"]:
        bullets.append(
            f"Temperature exceeded the safe range for "
            f"{_minutes(assessment.minutes_outside_safe_range)}"
        )
    if assessment.refrigeration_risk >= THRESHOLDS["refrigeration"]:
        unit = f" (unit {assessment.machine_code})" if assessment.machine_code else ""
        if assessment.cooling_efficiency_drop >= 1:
            bullets.append(
                f"Refrigeration efficiency dropped "
                f"{assessment.cooling_efficiency_drop:.0f}%{unit}"
            )
        else:
            bullets.append(
                f"Refrigeration health is degraded{unit} "
                f"({100 - assessment.refrigeration_risk:.0f}% health)"
            )
    if assessment.traffic_risk >= THRESHOLDS["traffic"]:
        bullets.append(
            f"Traffic added {_minutes(assessment.traffic_delay_minutes)} to the route"
        )
    if assessment.weather_risk >= THRESHOLDS["weather"]:
        phrase = WEATHER_PHRASE.get(assessment.weather_level, assessment.weather_level.lower())
        bullets.append(f"Route weather has deteriorated to {phrase}")
    if assessment.shelf_life_risk >= THRESHOLDS["shelf_life"]:
        bullets.append(
            f"Remaining shelf life is only {_hours(assessment.remaining_shelf_life_hours)}"
        )
    if assessment.eta_risk >= THRESHOLDS["eta"]:
        if assessment.eta_margin_hours < 0:
            bullets.append(
                f"Current route arrives outside the safe delivery window "
                f"(short by {_hours(abs(assessment.eta_margin_hours))})"
            )
        else:
            bullets.append(
                f"Only {_hours(assessment.eta_margin_hours)} of margin remain between "
                "arrival and shelf-life expiry"
            )

    if not bullets:
        bullets.append("All risk components are within normal operating range")
    return bullets


def explain_risk(shipment: Shipment, assessment: RiskAssessment) -> dict:
    status = band_for(assessment.melt_index)
    return {
        "headline": f"Shipment {shipment.code} is {status} because:",
        "status": status,
        "melt_index": round(assessment.melt_index),
        "bullets": risk_bullets(assessment),
        "contributions": contribution_breakdown(assessment),
        "disclaimer": (
            "Melt Index is a decision-support estimate produced by a transparent "
            "weighted formula, not a validated scientific measurement."
        ),
    }


def contribution_breakdown(assessment: RiskAssessment) -> list[dict]:
    """Per-component score, weight, and weighted points — the bar chart on the
    Shipment Detail page reads straight off this."""
    rows = [
        ("Temperature", assessment.temperature_risk, WEIGHTS["temperature"]),
        ("Refrigeration", assessment.refrigeration_risk, WEIGHTS["refrigeration"]),
        ("Traffic", assessment.traffic_risk, WEIGHTS["traffic"]),
        ("Weather", assessment.weather_risk, WEIGHTS["weather"]),
        ("Shelf life", assessment.shelf_life_risk, WEIGHTS["shelf_life"]),
        ("ETA margin", assessment.eta_risk, WEIGHTS["eta"]),
    ]
    return [
        {
            "component": name,
            "score": round(score, 1),
            "weight": weight,
            "points": round(score * weight, 2),
        }
        for name, score, weight in rows
    ]


def explain_recommendation(shipment: Shipment, result: OptimizationResult) -> str:
    """The AI recommendation sentence shown on the Shipment Detail page."""
    if result.recommended is None or result.current is None:
        return f"No alternative routes are registered for {shipment.code}."

    rec, cur = result.recommended, result.current
    if rec.route.id == cur.route.id:
        return (
            f"Stay on {cur.route.label}. It already carries the lowest expected loss "
            f"({inr(cur.expected_loss_inr)}) of the {len(result.evaluations)} routes evaluated."
        )

    reasons: list[str] = []
    if rec.components.traffic_risk < cur.components.traffic_risk - 5:
        reasons.append(
            f"avoids {_minutes(cur.components.traffic_delay_minutes - rec.components.traffic_delay_minutes)} of traffic delay"
        )
    if rec.components.refrigeration_risk < cur.components.refrigeration_risk - 5:
        reasons.append(
            f"moves the load to a reefer at {rec.components.reefer_health:.0f}% health "
            f"(current unit is at {cur.components.reefer_health:.0f}%)"
        )
    if rec.components.weather_risk < cur.components.weather_risk - 5:
        reasons.append("keeps the load out of the deteriorating weather corridor")
    if rec.components.eta_risk < cur.components.eta_risk - 5:
        reasons.append("arrives back inside the safe delivery window")

    reason_text = "; it " + ", ".join(reasons) if reasons else ""
    warning = (
        " No route fully satisfies the shelf-life window — this option minimizes damage."
        if result.no_safe_option
        else ""
    )
    return (
        f"Reroute {shipment.code} to {rec.route.label} and prioritize delivery. "
        f"Expected loss falls from {inr(cur.expected_loss_inr)} to "
        f"{inr(rec.expected_loss_inr)}, avoiding {inr(result.loss_avoided_inr)}"
        f"{reason_text}.{warning}"
    )


def explain_machine(machine, assessment) -> dict:
    """Plain-language reason for a machine's health verdict (§17 + §24)."""
    if assessment.insufficient_data:
        return {
            "headline": f"{machine.code}: not enough sensor history to predict failure.",
            "bullets": [
                "Fewer than 6 readings recorded — prediction skipped rather than guessed."
            ],
        }
    bullets = [f["detail"] for f in assessment.top_risk_factors]
    if assessment.anomaly_detected:
        bullets.insert(
            0,
            f"Anomaly detector flagged the latest readings "
            f"(anomaly score {assessment.anomaly_score:.2f})",
        )
    runway = runway_sentence(assessment.estimated_failure_hours)
    if runway:
        bullets.append(runway)
    if not bullets:
        bullets.append("Sensor readings are within nominal range")
    return {
        "headline": (
            f"{machine.code} is {assessment.status} (condition risk "
            f"{assessment.failure_probability * 100:.0f}%"
            + (
                f"; {assessment.ml_failure_probability * 100:.0f}% chance of failure within 24h"
                if assessment.ml_failure_probability is not None
                else ""
            )
            + ") because:"
        ),
        "bullets": bullets,
    }
