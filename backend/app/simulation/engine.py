"""The simulation engine.

There is exactly one way state changes in this build:

    apply a root cause  ->  integrate the world forward  ->  re-derive everything

`trigger_event` does the first step and then hands off to `physics.settle`,
which runs the same tick the background loop runs. A trigger therefore cannot
produce a state the live simulation could not have reached on its own, and it
never states what any prediction should become.

The background loop (`physics_loop`) runs the identical tick continuously, so
the dashboard is live whether or not anyone is pressing buttons - including for
the hero assets, which are no longer frozen between presses.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.ml.synthetic import NOMINAL_EFFICIENCY, efficiency_for_health
from app.models import Machine, Shipment, SimulationEvent
from app.seed_config import BASELINE_DEGRADATION_RATE
from app.seeding import reseed
from app.providers.base import LIVE, label_for_source
from app.services import maintenance, risk_engine, weather
from app.simulation import lifecycle, physics, scenarios

log = logging.getLogger("opsgenie.simulation")


class SimulationError(ValueError):
    """Raised for an unknown event type or a missing target."""


# ---------------------------------------------------------------------------
# Applying a root cause
# ---------------------------------------------------------------------------


def _apply_shipment_cause(db: Session, shipment: Shipment, scenario: scenarios.Scenario) -> str:
    """Traffic incidents land on the lane the shipment is actually taking."""
    route = risk_engine.selected_route(shipment)
    if route is None:
        raise SimulationError(f"{shipment.code} has no route to apply the event to.")
    if scenario.cause != "incident_delay_minutes":
        raise SimulationError(f"Cause '{scenario.cause}' does not apply to a shipment.")
    route.incident_delay_minutes = float(route.incident_delay_minutes) + scenario.amount
    if scenario.traffic_level:
        route.traffic_level = scenario.traffic_level
    # delay_minutes is NOT set here. The next tick recomputes it as
    # incident + congestion + weather, which is the only place it comes from.
    return route.label


def _apply_machine_cause(db: Session, machine: Machine, scenario: scenarios.Scenario) -> None:
    """Degradation raises the WEAR RATE; repair restores it.

    Note what is absent: no health score is written, no sensor outlier is
    injected. Efficiency now falls because the rate says it should, sensors are
    generated from that efficiency every tick, and the anomaly detector picks up
    a genuine drift rather than a planted outlier.
    """
    if scenario.cause == "degradation_rate_per_hour":
        machine.degradation_rate_per_hour = scenario.amount
    elif scenario.cause == "repair":
        machine.degradation_rate_per_hour = BASELINE_DEGRADATION_RATE
        machine.cooling_efficiency = round(
            min(NOMINAL_EFFICIENCY, float(machine.baseline_cooling_efficiency)), 2
        )
        maintenance.refresh(db, machine)
    else:
        raise SimulationError(f"Cause '{scenario.cause}' does not apply to a machine.")


def _apply_environment_cause(db: Session, scenario: scenarios.Scenario) -> None:
    """Weather injection. Recorded as SIMULATED_INJECTED, never as live."""
    state = physics.environment(db)
    if scenario.cause != "ambient_offset_c":
        raise SimulationError(f"Cause '{scenario.cause}' does not apply to the environment.")
    state.ambient_offset_c = scenario.amount
    state.weather_mode = "HEAT_STORM" if scenario.amount > 0 else "AUTO"


def trigger_event(db: Session, event_type: str, target_id: int | None = None) -> dict:
    """Apply one root cause, integrate forward, return the resulting state."""
    scenario = scenarios.get(event_type)
    if scenario is None:
        raise SimulationError(
            f"Unknown event_type '{event_type}'. Known: {sorted(scenarios.SCENARIOS)}"
        )

    machine: Machine | None = None
    target_label = ""
    resolved_target_id = 0

    if scenario.target_type == "machine":
        machine = (
            db.get(Machine, target_id)
            if target_id
            else db.query(Machine).filter(Machine.code == scenario.target_code).one_or_none()
        )
        if machine is None:
            raise SimulationError(f"Machine not found for event '{event_type}'.")
        _apply_machine_cause(db, machine, scenario)
        target_label = machine.code
        resolved_target_id = machine.id
    elif scenario.target_type == "shipment":
        shipment = (
            db.get(Shipment, target_id)
            if target_id
            else db.query(Shipment).filter(Shipment.code == scenario.target_code).one_or_none()
        )
        if shipment is None:
            raise SimulationError(f"Shipment not found for event '{event_type}'.")
        target_label = _apply_shipment_cause(db, shipment, scenario)
        resolved_target_id = shipment.id
    else:
        _apply_environment_cause(db, scenario)
        target_label = "all lanes"
        resolved_target_id = 0

    db.add(
        SimulationEvent(
            event_type=event_type,
            target_type=scenario.target_type,
            target_id=resolved_target_id,
            payload_json=json.dumps(
                {
                    "label": scenario.label,
                    "cause": scenario.cause,
                    "amount": scenario.amount,
                    "applied_to": target_label,
                    "settle_minutes": scenario.settle_minutes,
                }
            ),
        )
    )
    db.flush()

    # Integrate forward. Everything the response reports is a consequence.
    settle = physics.settle(db, scenario.settle_minutes, rng=random.Random(scenario.order * 97))

    shipments = db.query(Shipment).order_by(Shipment.melt_index.desc()).all()
    if machine is not None:
        db.refresh(machine)

    return {
        "event_type": event_type,
        "label": scenario.label,
        "description": scenario.description,
        "cause": {
            "field": scenario.cause,
            "amount": scenario.amount,
            "applied_to": target_label,
            "description": scenario.cause_description,
        },
        "simulated_minutes_advanced": settle.get("settled_minutes"),
        "machine": (
            {
                "id": machine.id,
                "code": machine.code,
                "health_score": machine.health_score,
                "cooling_efficiency": machine.cooling_efficiency,
                "degradation_rate_per_hour": machine.degradation_rate_per_hour,
                "failure_probability": machine.failure_probability,
                "status": machine.status,
                "anomaly_detected": machine.anomaly_detected,
                "anomaly_score": machine.anomaly_score,
            }
            if machine is not None
            else None
        ),
        "shipments": [
            {
                "id": s.id,
                "code": s.code,
                "melt_index": round(s.melt_index),
                "status": s.status,
                "cargo_temperature_c": s.cargo_temperature_c,
                "minutes_outside_safe_range": round(s.minutes_outside_safe_range, 1),
                "spoilage_probability": s.spoilage_probability,
                "expected_loss_inr": s.expected_loss_inr,
            }
            for s in shipments
        ],
    }


def reset(db: Session) -> dict:
    """Restore the seeded baseline and zero the simulation clock."""
    reseed(db)
    hero = db.query(Shipment).filter(Shipment.is_hero.is_(True)).first()
    state = physics.environment(db)
    return {
        "reset": True,
        "sim_minutes": state.sim_minutes,
        "hero_shipment": (
            {
                "code": hero.code,
                "melt_index": round(hero.melt_index),
                "status": hero.status,
                "cargo_temperature_c": hero.cargo_temperature_c,
            }
            if hero
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Background loops
# ---------------------------------------------------------------------------


def _advance_episode(db: Session, rng: random.Random, now: float) -> None:
    """One live tick, or a fresh episode if this one has run its course."""
    with lifecycle.WORLD_LOCK:
        state = physics.environment(db)
        if settings.auto_reset_enabled and lifecycle.needs_episode_reset(
            float(state.sim_minutes),
            lifecycle.activity().last_action,
            now,
            settings.episode_sim_hours,
            settings.action_grace_minutes,
        ):
            log.info(
                "Episode reached %.0f simulated hours unattended - resetting to baseline.",
                state.sim_minutes / 60.0,
            )
            reset(db)
            return
        physics.tick(db, None, rng)


def reset_if_stale(now: float | None = None) -> bool:
    """Called before serving a request: reset if the visitor is returning to a stale board."""
    if not settings.auto_reset_enabled:
        return False
    now = time.monotonic() if now is None else now
    if not lifecycle.needs_idle_reset(
        lifecycle.activity().last_request, now, settings.idle_reset_minutes
    ):
        return False
    with lifecycle.WORLD_LOCK:
        # Re-check under the lock: a concurrent request may have just reset.
        if not lifecycle.needs_idle_reset(
            lifecycle.activity().last_request, now, settings.idle_reset_minutes
        ):
            return False
        db = SessionLocal()
        try:
            log.info("Visitor returned after %.0f min idle - resetting to baseline.",
                     (now - lifecycle.activity().last_request) / 60.0)
            reset(db)
        finally:
            db.close()
        lifecycle.note_request(is_action=False, now=now)
    return True


async def physics_loop() -> None:
    """The live simulation. One tick every `physics_tick_seconds`.

    Runs for every asset, hero included. A control tower whose sensor feed
    stops between button presses is a slideshow.
    """
    rng = random.Random(20240)
    interval = settings.physics_tick_seconds
    log.info(
        "Physics loop: every %.1fs advancing %.1f simulated minutes.",
        interval,
        settings.sim_minutes_per_tick,
    )
    while True:
        try:
            await asyncio.sleep(interval)
            seen = lifecycle.activity()
            now = time.monotonic()
            if settings.auto_reset_enabled and lifecycle.is_paused(
                seen.last_request, now, settings.idle_pause_seconds
            ):
                # Nobody is watching. An unwatched world must not age.
                continue
            db = SessionLocal()
            try:
                await asyncio.to_thread(_advance_episode, db, rng, now)
            finally:
                db.close()
        except asyncio.CancelledError:
            log.info("Physics loop stopped.")
            raise
        except Exception:  # noqa: BLE001 - a demo must not die on one bad tick
            log.exception("Physics tick failed; continuing.")


async def weather_loop() -> None:
    """Refresh Open-Meteo on its own, slower schedule.

    Kept separate from the physics tick so a slow or unreachable API can never
    stall the simulation - the tick always reads the last stored observation.
    """
    log.info("Weather loop: Open-Meteo every %.0fs.", settings.weather_refresh_seconds)
    while True:
        db = SessionLocal()
        try:
            points = await asyncio.to_thread(physics.waypoints, db)
            state = physics.environment(db)
            sources = await asyncio.to_thread(
                weather.refresh, db, points, state.sim_minutes
            )
            db.commit()
            live = sum(1 for s in sources.values() if label_for_source(s) == LIVE)
            log.info("Weather refreshed: %d/%d waypoints live.", live, len(sources))
        except asyncio.CancelledError:
            log.info("Weather loop stopped.")
            raise
        except Exception:  # noqa: BLE001
            log.exception("Weather refresh failed; last observation stands.")
        finally:
            db.close()
        try:
            await asyncio.sleep(settings.weather_refresh_seconds)
        except asyncio.CancelledError:
            log.info("Weather loop stopped.")
            raise
