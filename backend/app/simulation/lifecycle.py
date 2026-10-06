"""The demo world's lifecycle: when it runs, and when it starts over.

The physics loop integrates forever, and nothing in the world ever finishes -
shipments never deliver, stock is never replenished. Left running for a day the
board drifts into a state nobody would demo: every warehouse at zero, every
shelf life spent. That is fine on a laptop where the presenter presses Reset,
and fatal on a hosted link a judge opens a week after submission.

So the world is treated as a bounded EPISODE:

  * PAUSE  - no dashboard has polled for `idle_pause_seconds`, so nobody is
             watching. The tick is skipped. An unwatched world does not age.
  * IDLE RESET - the first request after `idle_reset_minutes` of silence resets
             to the seeded baseline, so a returning visitor always lands on the
             same opening board.
  * EPISODE CAP - `episode_sim_hours` of simulated time have passed and nobody
             has pressed anything for `action_grace_minutes`. A tab left open
             all afternoon starts over instead of decaying; a presenter who is
             mid-demo is never interrupted, because their presses count.

The decisions are pure functions of timestamps so they can be tested without a
clock. `WORLD_LOCK` serialises every writer of world state (tick, reset,
trigger) - they previously ran on separate threads with nothing between them.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from app.config import settings

WORLD_LOCK = threading.Lock()


@dataclass
class Activity:
    """Monotonic timestamps of the last request and the last deliberate action."""

    last_request: float
    last_action: float


_activity = Activity(last_request=time.monotonic(), last_action=time.monotonic())


def note_request(is_action: bool, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    _activity.last_request = now
    if is_action:
        _activity.last_action = now


def activity() -> Activity:
    return _activity


def is_paused(last_request: float, now: float, idle_pause_seconds: float) -> bool:
    """Nobody is watching, so the world should not age."""
    return now - last_request > idle_pause_seconds


def needs_idle_reset(last_request: float, now: float, idle_reset_minutes: float) -> bool:
    """A visitor is arriving after long enough away that the board has gone stale."""
    return now - last_request > idle_reset_minutes * 60.0


def needs_episode_reset(
    sim_minutes: float,
    last_action: float,
    now: float,
    episode_sim_hours: float,
    action_grace_minutes: float,
) -> bool:
    """The episode has run its course and nobody is in the middle of driving it."""
    if sim_minutes < episode_sim_hours * 60.0:
        return False
    return now - last_action > action_grace_minutes * 60.0


def episode_payload(sim_minutes: float) -> dict:
    """What the dashboard shows about the episode, so a reset is never a surprise."""
    return {
        "auto_reset": settings.auto_reset_enabled,
        "sim_hours_elapsed": round(sim_minutes / 60.0, 1),
        "episode_sim_hours": settings.episode_sim_hours,
    }
