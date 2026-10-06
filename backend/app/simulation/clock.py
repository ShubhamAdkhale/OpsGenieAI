"""Twin time: the one clock every record in the digital twin is stamped with.

Before this module there were three clocks on screen at once. The header showed
the simulation's time of day ("07:18"), alerts and workflows were stamped with
the server's wall clock, and - because SQLite drops the timezone - the browser
then read those UTC stamps as local time, so they were also 5.5 hours off. A
judge could see "07:18" in the header beside an alert raised at "11:20 am".

Twin time is defined as midnight IST on the day the episode was reset, plus the
simulation's `sim_minutes`. The episode opens at 06:00 twin time and advances
at the simulation's pace (two twin hours per real minute by default), so an
alert raised mid-demo is stamped with the twin moment it happened.

Deliberately NOT on this clock: live weather observations. They are real
readings from Open-Meteo and keep their real observation time.

This module imports nothing from the app, so the ORM column defaults can use
`now` without a cycle. `physics.environment()` and `physics.tick()` keep the
cached state in step with the database row.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), name="IST")

_epoch: datetime | None = None
_sim_minutes: float = 0.0


def wall_now() -> datetime:
    return datetime.now(timezone.utc)


def epoch_for(started_at: datetime) -> datetime:
    """Midnight IST on the day `started_at` falls on, as an aware UTC datetime."""
    if started_at.tzinfo is None:  # SQLite hands back naive UTC
        started_at = started_at.replace(tzinfo=timezone.utc)
    local = started_at.astimezone(IST)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc)


def sync(started_at: datetime | None, sim_minutes: float) -> None:
    """Point the cache at an episode. Called whenever the clock row is read or moved."""
    global _epoch, _sim_minutes
    _epoch = epoch_for(started_at) if started_at is not None else None
    _sim_minutes = float(sim_minutes)


def at(sim_minutes: float) -> datetime:
    """Twin time for an arbitrary point in the current episode."""
    if _epoch is None:
        return wall_now()
    return _epoch + timedelta(minutes=float(sim_minutes))


def now() -> datetime:
    """The current twin time (aware UTC). Falls back to wall time before any episode."""
    return at(_sim_minutes)
