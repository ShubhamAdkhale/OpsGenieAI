"""Environment-driven configuration (§34: no secrets in code)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# backend/app/config.py -> backend/app -> backend -> repo root
BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Plain object rather than BaseSettings — fewer moving parts to debug."""

    def __init__(self) -> None:
        raw_url = os.getenv("DATABASE_URL", "sqlite:///./opsgenie.db")
        # Resolve the default relative SQLite path against the repo root so the
        # DB file lands in the same place no matter which directory uvicorn or
        # pytest was launched from.
        if raw_url.startswith("sqlite:///./"):
            db_path = REPO_ROOT / raw_url.removeprefix("sqlite:///./")
            raw_url = f"sqlite:///{db_path.as_posix()}"
        self.database_url: str = raw_url

        origins = os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        )
        self.cors_origins: list[str] = [o.strip() for o in origins.split(",") if o.strip()]

        self.use_ml_spoilage: bool = _as_bool(os.getenv("USE_ML_SPOILAGE"), default=False)

        # --- Live physics simulation ------------------------------------
        # The causal core. Every operational number is integrated forward by
        # this loop rather than assigned, so switching it off freezes the world
        # at its seeded state instead of making the numbers wrong.
        self.physics_enabled: bool = _as_bool(os.getenv("PHYSICS_ENABLED"), default=True)
        # Wall-clock seconds between ticks.
        self.physics_tick_seconds: float = float(os.getenv("PHYSICS_TICK_SECONDS", "3"))
        # Simulated minutes advanced per tick. Together with the line above this
        # sets the demo's pace: 6 min per 3 s means one real minute of watching
        # is two simulated hours of transit, so a degradation is visible while
        # someone is still talking about it.
        self.sim_minutes_per_tick: float = float(os.getenv("SIM_MINUTES_PER_TICK", "6"))
        # Simulated minutes a scenario trigger settles for before responding.
        # Integration step used while settling a triggered event. Coarser than
        # the live tick purely for speed: the box has a ~3.3 h thermal time
        # constant, so a 15-minute Euler step tracks it closely.
        self.settle_step_minutes: float = float(os.getenv("SETTLE_STEP_MINUTES", "15"))

        # --- Demo lifecycle (simulation/lifecycle.py) -------------------
        # Nothing in the world ever finishes, so an unattended board decays.
        # These bound it into an episode that always restarts cleanly.
        self.auto_reset_enabled: bool = _as_bool(os.getenv("AUTO_RESET_ENABLED"), default=True)
        # No poll for this long means nobody is watching: skip the tick.
        self.idle_pause_seconds: float = float(os.getenv("IDLE_PAUSE_SECONDS", "90"))
        # First request after this much silence resets to the seeded baseline.
        self.idle_reset_minutes: float = float(os.getenv("IDLE_RESET_MINUTES", "20"))
        # Simulated hours an episode may run before it starts over (24 h is
        # twelve real minutes at the default pace; the full arc uses ~10 h)...
        self.episode_sim_hours: float = float(os.getenv("EPISODE_SIM_HOURS", "24"))
        # ...but never while someone pressed a button this recently.
        self.action_grace_minutes: float = float(os.getenv("ACTION_GRACE_MINUTES", "5"))

        # --- Weather (Open-Meteo) ---------------------------------------
        self.weather_enabled: bool = _as_bool(os.getenv("WEATHER_ENABLED"), default=True)
        self.weather_timeout_seconds: float = float(os.getenv("WEATHER_TIMEOUT_SECONDS", "4"))
        self.weather_refresh_seconds: float = float(os.getenv("WEATHER_REFRESH_SECONDS", "600"))

        self.ml_model_dir: Path = BACKEND_DIR / "app" / "ml" / "models"

        # Built frontend for single-service deployment (see Dockerfile). Absent
        # in development, where Vite serves the UI and proxies /api.
        self.static_dir: Path = Path(os.getenv("STATIC_DIR", str(BACKEND_DIR / "static")))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
