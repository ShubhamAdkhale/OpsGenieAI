"""Weather as the rest of the app sees it: persistence, banding and delay.

The FETCHING moved to `app/providers/weather/` in the ingestion refactor, and
the live-else-simulated decision moved to `ProviderChain`. What stays here is
everything that is about this application rather than about a data source:
storing observations with their provenance, pruning them, reading the latest
one per city, and the two pure functions the risk engine calls.

Two things come out of a reading and both matter downstream:

* `weather_level`  -> the CLEAR/RAIN/STORM/EXTREME band `risk_engine` already
  weights at 0.15, plus a route-delay multiplier.
* `temperature_c`  -> the AMBIENT temperature in the cargo thermal model. This
  is the causal link: external temperature up means more heat ingress, which
  means the reefer has to work harder to hold its setpoint, and a degraded
  reefer loses that race.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import WeatherObservation
from app.providers import registry
from app.providers.base import (
    LIVE_OPEN_METEO,
    SIMULATED_FALLBACK,
    SIMULATED_INJECTED,
    FetchContext,
)
from app.providers.weather.model import (
    DRIZZLE_CODES,
    HEAT_EXTREME_C,
    HEAT_STORM_C,
    RAIN_CODES,
    THUNDERSTORM_CODES,
    WEATHER_DELAY_FACTOR,
    Waypoint,
    classify,
    delay_factor,
)
from app.providers.weather.simulated import PROVIDER as SIMULATED_PROVIDER

log = logging.getLogger("opsgenie.weather")

# Persisted source strings. Re-exported here because they are stored on
# WeatherObservation.source and read back all over the app; the definitions
# live in `providers.base` so a provider can declare its own.
LIVE = LIVE_OPEN_METEO
FALLBACK = SIMULATED_FALLBACK
INJECTED = SIMULATED_INJECTED

__all__ = [
    "LIVE",
    "FALLBACK",
    "INJECTED",
    "Waypoint",
    "classify",
    "delay_factor",
    "simulate",
    "refresh",
    "prune",
    "latest",
    "latest_all",
    "is_stale",
    "WEATHER_DELAY_FACTOR",
    "THUNDERSTORM_CODES",
    "RAIN_CODES",
    "DRIZZLE_CODES",
    "HEAT_EXTREME_C",
    "HEAT_STORM_C",
]


def simulate(waypoint: Waypoint, sim_minutes: float) -> dict:
    """The simulated reading for one waypoint, bypassing the chain.

    Two callers genuinely want the fallback specifically rather than "whatever
    is best available": seeding, which must stay offline so a reset is instant
    and tests never touch the network, and the thermal model's last-ditch path
    when a lane has no stored observation at all.
    """
    return SIMULATED_PROVIDER.one(waypoint, sim_minutes)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def refresh(db: Session, waypoints: list[Waypoint], sim_minutes: float) -> dict[str, str]:
    """Fetch every waypoint through the chain and store one observation each.

    Returns {city: source} so the caller can log it and the API can report
    which waypoints are genuinely live. Fallback is per waypoint, so a partial
    Open-Meteo answer stores the live rows it did return rather than discarding
    them for consistency with the ones it did not.
    """
    if not waypoints:
        return {}
    answered = registry.chain("weather").fetch(
        waypoints, FetchContext(sim_minutes=sim_minutes)
    )
    sources: dict[str, str] = {}
    for waypoint in waypoints:
        values = answered.get(waypoint.key)
        if values is None:
            # Unreachable while the terminal provider is the simulator, but a
            # missing observation would leave the thermal model with no ambient.
            values = simulate(waypoint, sim_minutes)
        db.add(
            WeatherObservation(city=waypoint.city, lat=waypoint.lat, lon=waypoint.lon, **values)
        )
        sources[waypoint.city] = values["source"]
    db.flush()
    prune(db)
    return sources


def prune(db: Session, keep_hours: float = 12.0) -> None:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=keep_hours)
    db.query(WeatherObservation).filter(WeatherObservation.observed_at < cutoff).delete(
        synchronize_session=False
    )


def latest(db: Session, city: str) -> WeatherObservation | None:
    return (
        db.query(WeatherObservation)
        .filter(WeatherObservation.city == city)
        .order_by(WeatherObservation.id.desc())
        .first()
    )


def latest_all(db: Session) -> list[WeatherObservation]:
    """Most recent observation per city."""
    seen: dict[str, WeatherObservation] = {}
    rows = db.query(WeatherObservation).order_by(WeatherObservation.id.desc()).limit(300).all()
    for row in rows:
        seen.setdefault(row.city, row)
    return list(seen.values())


def is_stale(observation: WeatherObservation | None, max_age_seconds: float) -> bool:
    if observation is None:
        return True
    observed = observation.observed_at
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - observed).total_seconds() > max_age_seconds
