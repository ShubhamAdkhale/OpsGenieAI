"""Melt Index, spoilage, expected loss and route optimization (§18 §19 §20).

The Melt Index is a DETERMINISTIC weighted formula, not a learned model. That
is a deliberate choice (§15): a judge or an ops manager must be able to see
exactly why the number moved, and a formula is instantly auditable while a
black box is not.

Nothing here is scientifically validated. It is a decision-support score for a
hackathon demo, and the UI says so on screen.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.config import settings
from app.models import DELIVERED, Machine, Product, RiskAssessment, Route, Shipment

# ---------------------------------------------------------------------------
# Tuning constants — THE most important knobs in the whole app (§18).
# Adjust these, not inline numbers, when re-tuning the scripted demo arc.
# ---------------------------------------------------------------------------

WEIGHTS: dict[str, float] = {
    "temperature": 0.25,
    "refrigeration": 0.20,
    "traffic": 0.15,
    "weather": 0.15,
    "shelf_life": 0.15,
    "eta": 0.10,
}

# Minutes of cold-chain excursion that count as 100 TemperatureRisk.
TEMP_MINUTES_FULL_RISK = 240.0
# Minutes of traffic delay that count as 100 TrafficRisk (§18: delay/60 x 100).
TRAFFIC_MINUTES_FULL_RISK = 60.0
# §18 weather lookup.
WEATHER_RISK = {"CLEAR": 0.0, "RAIN": 40.0, "STORM": 70.0, "EXTREME": 100.0}
# ETARisk drops 20 points per hour of margin, so 5h of margin means zero risk.
ETA_RISK_PER_MARGIN_HOUR = 20.0
# Cooling efficiency floor used by the RUL heuristic and the "healthy" baseline.
NOMINAL_COOLING_EFFICIENCY = 95.0

# Logistic mapping melt index -> spoilage probability (§19 fallback / default).
# Calibrated so the scripted demo lands on the §7 numbers:
#   melt 88.71 -> 0.820 -> Route A expected loss Rs 4,10,000
#   melt 38.52 -> 0.211 -> Route B expected loss Rs 1,05,000
SPOILAGE_MIDPOINT = 61.9
SPOILAGE_SCALE = 17.7

# §20: a route may arrive this many hours past the shelf-life expiry and still
# count as "feasible" — accounts for the score being an estimate, not a clock.
SHELF_LIFE_BUFFER_HOURS = 0.5

BANDS = [(20, "SAFE"), (40, "LOW"), (60, "MODERATE"), (80, "HIGH"), (100, "CRITICAL")]


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def band_for(melt_index: float) -> str:
    """§18 bands, applied to the DISPLAYED (rounded) value so the badge and the
    number on screen can never disagree."""
    rounded = round(melt_index)
    for ceiling, name in BANDS:
        if rounded <= ceiling:
            return name
    return "CRITICAL"


def round_inr(amount: float) -> float:
    """Round to the nearest Rs 1,000 — these are estimates, not invoices."""
    return math.floor(amount / 1000.0 + 0.5) * 1000.0


# ---------------------------------------------------------------------------
# Risk components
# ---------------------------------------------------------------------------


@dataclass
class RiskComponents:
    temperature_risk: float
    refrigeration_risk: float
    traffic_risk: float
    weather_risk: float
    shelf_life_risk: float
    eta_risk: float
    melt_index: float
    # Raw inputs, kept so §24 can build its sentences from stored data alone.
    minutes_outside_safe_range: float
    projected_excursion_minutes: float
    cooling_efficiency_drop: float
    traffic_delay_minutes: float
    remaining_shelf_life_hours: float
    weather_level: str
    machine_code: str
    reefer_health: float
    transit_hours: float
    eta_margin_hours: float
    route_label: str

    def as_dict(self) -> dict:
        return asdict(self)


def reefer_health_for(shipment: Shipment, route: Route | None) -> float:
    """Health of the refrigeration unit that WOULD carry the goods on `route`.

    An alternative route may pass through a cold hub and transfer the load to a
    healthy standby reefer; that route then carries its own health figure.
    """
    if route is not None and route.reefer_health_override is not None:
        return float(route.reefer_health_override)
    machine: Machine | None = shipment.machine
    if machine is None:
        return 100.0
    return float(machine.health_score)


def compute_components(
    shipment: Shipment,
    product: Product,
    route: Route | None,
) -> RiskComponents:
    """Evaluate the §18 formula for one shipment travelling one specific route."""
    reefer_health = reefer_health_for(shipment, route)
    machine = shipment.machine

    eta_minutes = float(route.eta_minutes) if route else 0.0
    delay_minutes = float(route.delay_minutes) if route else 0.0
    weather_level = route.weather_level if route else "CLEAR"
    transit_minutes = eta_minutes + delay_minutes
    transit_hours = transit_minutes / 60.0

    # TemperatureRisk — excursion already accumulated, plus the excursion this
    # route is projected to add. A degraded reefer leaks cold proportionally to
    # how far its health has fallen, so a longer trip on a healthy unit can be
    # safer than a shorter trip on a failing one.
    accumulated = float(shipment.minutes_outside_safe_range)
    projected_extra = transit_minutes * (1.0 - reefer_health / 100.0)
    projected_excursion = accumulated + projected_extra
    temperature_risk = clamp(projected_excursion / TEMP_MINUTES_FULL_RISK * 100.0)

    # RefrigerationRisk — pulled live from the linked Machine (§18).
    refrigeration_risk = clamp(100.0 - reefer_health)

    traffic_risk = clamp(delay_minutes / TRAFFIC_MINUTES_FULL_RISK * 100.0)
    weather_risk = WEATHER_RISK.get(weather_level, 0.0)

    shelf_hours = max(float(product.unit_shelf_life_hours), 1e-6)
    remaining = float(shipment.remaining_shelf_life_hours)
    shelf_life_risk = clamp(100.0 * (1.0 - remaining / shelf_hours))

    margin_hours = remaining - transit_hours
    if margin_hours < 0:
        eta_risk = 100.0
    else:
        eta_risk = clamp(100.0 - margin_hours * ETA_RISK_PER_MARGIN_HOUR)

    melt_index = clamp(
        WEIGHTS["temperature"] * temperature_risk
        + WEIGHTS["refrigeration"] * refrigeration_risk
        + WEIGHTS["traffic"] * traffic_risk
        + WEIGHTS["weather"] * weather_risk
        + WEIGHTS["shelf_life"] * shelf_life_risk
        + WEIGHTS["eta"] * eta_risk
    )

    # Efficiency drop is measured against the unit's own dispatch baseline, so
    # the §24 sentence reads "dropped 18%" rather than "18 points below the
    # factory nominal of a brand-new unit".
    if route is not None and route.reefer_health_override is not None:
        efficiency_drop = 0.0  # a standby unit starts fresh on this leg
    elif machine is not None:
        efficiency_drop = max(
            0.0, float(machine.baseline_cooling_efficiency) - float(machine.cooling_efficiency)
        )
    else:
        efficiency_drop = 0.0

    return RiskComponents(
        temperature_risk=temperature_risk,
        refrigeration_risk=refrigeration_risk,
        traffic_risk=traffic_risk,
        weather_risk=weather_risk,
        shelf_life_risk=shelf_life_risk,
        eta_risk=eta_risk,
        melt_index=melt_index,
        minutes_outside_safe_range=accumulated,
        projected_excursion_minutes=projected_excursion,
        cooling_efficiency_drop=efficiency_drop,
        traffic_delay_minutes=delay_minutes,
        remaining_shelf_life_hours=remaining,
        weather_level=weather_level,
        machine_code=machine.code if machine else "",
        reefer_health=reefer_health,
        transit_hours=transit_hours,
        eta_margin_hours=margin_hours,
        route_label=route.label if route else "No route assigned",
    )


# ---------------------------------------------------------------------------
# Spoilage probability and expected loss (§19)
# ---------------------------------------------------------------------------


def spoilage_from_melt_index(melt_index: float) -> float:
    """Deterministic calibrated curve.

    This is the DEFAULT path (see USE_ML_SPOILAGE in .env). It is used instead
    of the trained classifier during the demo because the demo must produce
    byte-identical numbers on every rehearsal (§38). The trained
    GradientBoostingClassifier is real, is trained against this curve, and is
    exercised by the test suite — flip USE_ML_SPOILAGE=true to route through it.
    """
    z = (melt_index - SPOILAGE_MIDPOINT) / SPOILAGE_SCALE
    return 1.0 / (1.0 + math.exp(-z))


def spoilage_probability(components: RiskComponents, shipment: Shipment) -> float:
    if settings.use_ml_spoilage:
        from app.ml.registry import predict_spoilage

        ml_value = predict_spoilage(components, shipment)
        if ml_value is not None:
            return ml_value
    return spoilage_from_melt_index(components.melt_index)


def expected_loss(shipment: Shipment, probability: float) -> float:
    """§19: expected_loss = shipment_value x spoilage_probability."""
    return round_inr(float(shipment.shipment_value_inr) * probability)


# ---------------------------------------------------------------------------
# Route evaluation and optimization (§20)
# ---------------------------------------------------------------------------


@dataclass
class RouteEvaluation:
    route: Route
    components: RiskComponents
    spoilage_probability: float
    expected_loss_inr: float
    feasible: bool

    def to_payload(self) -> dict:
        c = self.components
        return {
            "route_id": self.route.id,
            "label": self.route.label,
            "eta_minutes": self.route.eta_minutes,
            "delay_minutes": self.route.delay_minutes,
            "effective_eta_minutes": self.route.eta_minutes + self.route.delay_minutes,
            "traffic_level": self.route.traffic_level,
            "weather_level": self.route.weather_level,
            "is_current": self.route.is_current,
            "is_selected": self.route.is_selected,
            "notes": self.route.notes,
            "melt_index": round(c.melt_index, 1),
            "risk_status": band_for(c.melt_index),
            "spoilage_probability": round(self.spoilage_probability, 4),
            "expected_loss_inr": self.expected_loss_inr,
            "arrives_within_shelf_life": self.feasible,
            "eta_margin_hours": round(c.eta_margin_hours, 2),
            "reefer_health": round(c.reefer_health, 1),
        }


def evaluate_route(shipment: Shipment, product: Product, route: Route) -> RouteEvaluation:
    components = compute_components(shipment, product, route)
    probability = spoilage_probability(components, shipment)
    feasible = components.transit_hours <= (
        float(shipment.remaining_shelf_life_hours) + SHELF_LIFE_BUFFER_HOURS
    )
    return RouteEvaluation(
        route=route,
        components=components,
        spoilage_probability=probability,
        expected_loss_inr=expected_loss(shipment, probability),
        feasible=feasible,
    )


def evaluate_all_routes(shipment: Shipment) -> list[RouteEvaluation]:
    product = shipment.product
    return [evaluate_route(shipment, product, r) for r in shipment.routes]


def selected_route(shipment: Shipment) -> Route | None:
    for route in shipment.routes:
        if route.is_selected:
            return route
    for route in shipment.routes:
        if route.is_current:
            return route
    return shipment.routes[0] if shipment.routes else None


@dataclass
class OptimizationResult:
    evaluations: list[RouteEvaluation]
    current: RouteEvaluation | None
    recommended: RouteEvaluation | None
    loss_avoided_inr: float
    no_safe_option: bool

    @property
    def should_reroute(self) -> bool:
        return (
            self.current is not None
            and self.recommended is not None
            and self.recommended.route.id != self.current.route.id
            and self.loss_avoided_inr > 0
        )


def optimize(shipment: Shipment) -> OptimizationResult:
    """§20 — pick the route that minimizes EXPECTED BUSINESS LOSS, subject to
    arriving inside the shelf-life window. Deliberately not a general solver:
    a handful of candidate routes compared on one number the manager can read.
    """
    evaluations = evaluate_all_routes(shipment)
    if not evaluations:
        return OptimizationResult([], None, None, 0.0, False)

    current_route = selected_route(shipment)
    current = next(
        (e for e in evaluations if current_route is not None and e.route.id == current_route.id),
        evaluations[0],
    )

    feasible = [e for e in evaluations if e.feasible]
    no_safe_option = not feasible
    pool = feasible or evaluations
    recommended = min(pool, key=lambda e: (e.expected_loss_inr, e.components.transit_hours))

    loss_avoided = max(0.0, current.expected_loss_inr - recommended.expected_loss_inr)
    return OptimizationResult(
        evaluations=evaluations,
        current=current,
        recommended=recommended,
        loss_avoided_inr=loss_avoided,
        no_safe_option=no_safe_option,
    )


# ---------------------------------------------------------------------------
# Recalculation entry point — everything that changes state calls this (§10)
# ---------------------------------------------------------------------------


def recalculate(db: Session, shipment: Shipment) -> RiskAssessment:
    """Recompute the shipment's risk on its CURRENT route, persist an audit row.

    Every trigger — a simulation event, an approved reroute, a machine health
    change — funnels through this one function. That single shared code path is
    what makes the cross-module story in §5 true rather than staged.
    """
    product = shipment.product
    route = selected_route(shipment)
    components = compute_components(shipment, product, route)
    probability = spoilage_probability(components, shipment)

    shipment.melt_index = round(components.melt_index, 2)
    shipment.spoilage_probability = round(probability, 4)
    shipment.expected_loss_inr = expected_loss(shipment, probability)
    # A shipment that has already been rerouted keeps that terminal status; its
    # numbers still update so the manager can watch the risk come down.
    if shipment.status not in ("REROUTED", DELIVERED):
        shipment.status = band_for(components.melt_index)

    assessment = RiskAssessment(
        shipment_id=shipment.id,
        temperature_risk=round(components.temperature_risk, 2),
        refrigeration_risk=round(components.refrigeration_risk, 2),
        traffic_risk=round(components.traffic_risk, 2),
        weather_risk=round(components.weather_risk, 2),
        shelf_life_risk=round(components.shelf_life_risk, 2),
        eta_risk=round(components.eta_risk, 2),
        melt_index=round(components.melt_index, 2),
        minutes_outside_safe_range=round(components.minutes_outside_safe_range, 1),
        cooling_efficiency_drop=round(components.cooling_efficiency_drop, 1),
        traffic_delay_minutes=round(components.traffic_delay_minutes, 1),
        remaining_shelf_life_hours=round(components.remaining_shelf_life_hours, 2),
        weather_level=components.weather_level,
        machine_code=components.machine_code,
        eta_margin_hours=round(components.eta_margin_hours, 2),
        route_label=components.route_label,
    )
    db.add(assessment)
    db.flush()
    return assessment


def latest_assessment(db: Session, shipment_id: int) -> RiskAssessment | None:
    return (
        db.query(RiskAssessment)
        .filter(RiskAssessment.shipment_id == shipment_id)
        .order_by(RiskAssessment.id.desc())
        .first()
    )
