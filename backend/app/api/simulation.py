from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.serializers import iso
from app.config import settings
from app.database import get_db
from app.models import SimulationEvent
from app.schemas import SimulationTriggerRequest
from app.providers.base import LIVE, label_for_source
from app.services import provenance, weather
from app.simulation import clock, engine, lifecycle, physics, scenarios

router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.get("/scenarios")
def list_scenarios() -> dict:
    """Drives the Simulation Control Panel buttons (§28)."""
    return {
        "scenarios": scenarios.control_panel(),
        "demo_sequence": scenarios.DEMO_SEQUENCE,
        "hero": scenarios.HERO_CODES,
        "escalation_sequence": scenarios.ESCALATION_SEQUENCE,
        "causes": scenarios.CAUSES,
        "note": (
            "Each scenario changes ONE root cause and then lets the simulation "
            "integrate forward. No scenario can set a Melt Index, a spoilage "
            "probability or an excursion figure - those are derived."
        ),
    }


@router.post("/trigger-event")
def trigger_event(payload: SimulationTriggerRequest, db: Session = Depends(get_db)) -> dict:
    try:
        with lifecycle.WORLD_LOCK:
            return engine.trigger_event(db, payload.event_type, payload.target_id)
    except engine.SimulationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reset")
def reset(db: Session = Depends(get_db)) -> dict:
    """Restores the seeded baseline. Run this before every rehearsal (§35)."""
    with lifecycle.WORLD_LOCK:
        return engine.reset(db)


@router.get("/environment")
def environment(db: Session = Depends(get_db)) -> dict:
    """The simulation clock, the live weather feed and its provenance."""
    state = physics.environment(db)
    return {
        "sim_minutes": state.sim_minutes,
        "tick_count": state.tick_count,
        "weather_mode": state.weather_mode,
        "ambient_offset_c": round(state.ambient_offset_c, 2),
        "episode": lifecycle.episode_payload(state.sim_minutes),
        "twin_time": iso(clock.now()),
        "physics": {
            "enabled": settings.physics_enabled,
            "tick_seconds": settings.physics_tick_seconds,
            "sim_minutes_per_tick": settings.sim_minutes_per_tick,
        },
        "provenance": provenance.summary(db),
    }


@router.post("/tick")
def manual_tick(db: Session = Depends(get_db)) -> dict:
    """Advance the simulation by one step by hand.

    Useful when the background loop is disabled, and for stepping through the
    causal chain slowly while explaining it.
    """
    with lifecycle.WORLD_LOCK:
        return physics.tick(db)


@router.post("/refresh-weather")
def refresh_weather(db: Session = Depends(get_db)) -> dict:
    """Re-fetch Open-Meteo now instead of waiting for the scheduled refresh."""
    state = physics.environment(db)
    sources = weather.refresh(db, physics.waypoints(db), state.sim_minutes)
    db.commit()
    return {
        "refreshed": len(sources),
        "live": sum(1 for value in sources.values() if label_for_source(value) == LIVE),
        "sources": sources,
    }


@router.get("/events")
def list_events(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.query(SimulationEvent).order_by(SimulationEvent.id.desc()).limit(50).all()
    return [
        {
            "id": row.id,
            "event_type": row.event_type,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "payload": row.payload_json,
            "triggered_at": iso(row.triggered_at),
        }
        for row in rows
    ]
