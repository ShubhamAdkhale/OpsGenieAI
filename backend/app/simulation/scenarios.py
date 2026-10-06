"""Scenario definitions - one root cause each.

A scenario names a CAUSE and a magnitude. It cannot name a consequence: there
is no field here for a Melt Index, an excursion figure or a spoilage
probability, because a scenario that could set those would be a script rather
than a simulation.

The physics tick turns causes into consequences. See `simulation/physics.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.seed_config import DEMO_EVENTS, HERO_MACHINE_CODE, HERO_SHIPMENT_CODE

# The root causes a scenario is allowed to touch, and what each one means.
CAUSES = {
    "incident_delay_minutes": "Adds incident delay to the shipment's current lane.",
    "degradation_rate_per_hour": "Sets a machine's cooling-efficiency loss per hour.",
    "ambient_offset_c": "Shifts ambient temperature and re-bands lane weather.",
    "repair": "Restores a machine's wear rate and cooling efficiency.",
}


@dataclass
class Scenario:
    event_type: str
    label: str
    description: str
    order: int
    target_type: str  # shipment | machine | environment
    target_code: str
    cause: str
    amount: float
    settle_minutes: float
    traffic_level: str | None = None

    @property
    def cause_description(self) -> str:
        return CAUSES.get(self.cause, self.cause)


SCENARIOS: dict[str, Scenario] = {
    event_type: Scenario(
        event_type=event_type,
        label=spec["label"],
        description=spec["description"],
        order=spec["order"],
        target_type=spec["target_type"],
        target_code=spec["target_code"],
        cause=spec["cause"],
        amount=float(spec["amount"]),
        settle_minutes=float(spec["settle_minutes"]),
        traffic_level=spec.get("traffic_level"),
    )
    for event_type, spec in DEMO_EVENTS.items()
}

DEMO_SEQUENCE: list[str] = [
    s.event_type for s in sorted(SCENARIOS.values(), key=lambda s: s.order)
]

# The three escalations, in order. `maintenance_completed` is the recovery step
# and is deliberately excluded.
ESCALATION_SEQUENCE: list[str] = [
    s.event_type
    for s in sorted(SCENARIOS.values(), key=lambda s: s.order)
    if s.cause != "repair"
]

HERO_CODES = {"shipment": HERO_SHIPMENT_CODE, "machine": HERO_MACHINE_CODE}


def get(event_type: str) -> Scenario | None:
    return SCENARIOS.get(event_type)


def control_panel() -> list[dict]:
    """Payload behind the scenario buttons.

    Each button advertises the cause it applies, so the panel reads as "this
    changes an input" rather than "this sets a score".
    """
    return [
        {
            "event_type": s.event_type,
            "label": s.label,
            "description": s.description,
            "order": s.order,
            "target_type": s.target_type,
            "target_code": s.target_code,
            "cause": s.cause,
            "cause_description": s.cause_description,
            "amount": s.amount,
            "settle_minutes": s.settle_minutes,
        }
        for s in sorted(SCENARIOS.values(), key=lambda s: s.order)
    ]
