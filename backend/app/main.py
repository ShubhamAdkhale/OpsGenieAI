"""FastAPI application entry point.

    uvicorn app.main:app --reload --port 8000

Interactive docs at http://localhost:8000/docs — which doubles as the manual
testing tool during development (§11) and as the way to run the §7 script
without the UI.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api import (
    alerts,
    copilot,
    dashboard,
    forecast,
    machines,
    shipments,
    simulation,
    workflows,
)
from app.config import settings
from app.database import SessionLocal, create_all, get_db
from app.ml.registry import model_status
from app.seeding import seed_if_empty
from app.services import weather
from app.simulation import engine, lifecycle, physics
from app.simulation.engine import physics_loop, weather_loop

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("opsgenie")


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all()

    # Load every model BEFORE any background thread starts.
    #
    # The physics tick runs via asyncio.to_thread and calls into scikit-learn.
    # If the first such call happens concurrently with another thread importing
    # sklearn, CPython's import lock can deadlock and the model is reported as
    # failed for the rest of the process. Warming the registry here means all
    # imports happen once, on one thread, before there is anything to race.
    statuses = model_status()
    for name, status in statuses.items():
        if status["loaded"]:
            log.info("Model loaded: %s", name)
        else:
            log.warning(
                "Model NOT loaded (%s): %s — using the rule-based fallback.",
                name,
                status["error"],
            )

    db = SessionLocal()
    try:
        if seed_if_empty(db):
            log.info("Empty database detected — seeded the baseline demo state.")
        # Point twin time at the stored episode before the first request, so a
        # write that lands before the first tick is not stamped in wall time.
        physics.environment(db)
    finally:
        db.close()

    tasks: list[asyncio.Task] = []
    if settings.physics_enabled:
        tasks.append(asyncio.create_task(physics_loop()))
    else:
        log.info("Physics loop disabled — the world is frozen at its seeded state.")
    if settings.weather_enabled:
        tasks.append(asyncio.create_task(weather_loop()))
    else:
        log.info("Weather disabled — the simulated diurnal curve will be used.")

    yield

    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="OpsGenie AI",
    description=(
        "AI-powered Operations Control Tower. Predict the problem. Understand "
        "the impact. Take action.\n\n"
        "**All data served by this API is simulated.** Melt Index, spoilage "
        "probability and rupee figures are decision-support estimates, not "
        "guarantees, and workflow execution is simulated — no external courier, "
        "ERP or work-order system is called."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def track_activity(request: Request, call_next):
    """Feed the demo lifecycle (simulation/lifecycle.py).

    Every dashboard poll proves someone is watching; every non-GET is someone
    driving. A visitor returning to a long-idle board gets a fresh baseline
    BEFORE their first response, never a decayed one. `/api/health` is left
    out so an uptime monitor cannot keep an empty room awake.
    """
    path = request.url.path
    if path.startswith("/api") and path != "/api/health":
        await asyncio.to_thread(engine.reset_if_stale)
        lifecycle.note_request(is_action=request.method != "GET")
    return await call_next(request)


for router in (
    dashboard.router,
    shipments.router,
    machines.router,
    forecast.router,
    workflows.router,
    alerts.router,
    simulation.router,
    copilot.router,
):
    app.include_router(router, prefix="/api")


@app.get("/api/health", tags=["meta"])
def health(db: Session = Depends(get_db)) -> dict:
    """Shows at a glance which inputs are live and which are falling back."""
    return {
        "status": "ok",
        "database_url": settings.database_url,
        "use_ml_spoilage": settings.use_ml_spoilage,
        "physics": {
            "enabled": settings.physics_enabled,
            "tick_seconds": settings.physics_tick_seconds,
            "sim_minutes_per_tick": settings.sim_minutes_per_tick,
        },
        "weather": {
            "enabled": settings.weather_enabled,
            "provider": "open-meteo",
            "waypoints": [
                {"city": o.city, "source": o.source, "weather_level": o.weather_level}
                for o in weather.latest_all(db)
            ],
        },
        "models": model_status(),
    }


if settings.static_dir.is_dir():
    # Single-service deployment: the built React app ships inside the image
    # and is served from the same origin as the API, so the frontend's
    # relative `/api` calls need no CORS and no second URL. Unknown paths fall
    # back to index.html so client-side routes survive a page refresh.
    _static_root = settings.static_dir.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (_static_root / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(_static_root):
            return FileResponse(candidate)
        return FileResponse(_static_root / "index.html")

else:

    @app.get("/", tags=["meta"])
    def root() -> dict:
        return {
            "name": "OpsGenie AI",
            "tagline": "Predict the problem. Understand the impact. Take action.",
            "docs": "/docs",
            "api": "/api",
        }
