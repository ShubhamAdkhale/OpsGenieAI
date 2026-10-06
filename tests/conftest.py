"""Test fixtures.

The environment is configured BEFORE `app.*` is imported, because `app.config`
reads it at import time and caches the result.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TEST_DB = Path(tempfile.gettempdir()) / "opsgenie_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
# The background loops must not run during tests: each test drives the
# physics tick explicitly so it controls exactly how much simulated time
# has passed. Weather is forced off so no test ever touches the network -
# the labelled simulated fallback is deterministic.
os.environ["PHYSICS_ENABLED"] = "false"
os.environ["WEATHER_ENABLED"] = "false"
os.environ["USE_ML_SPOILAGE"] = "false"
# Tests drive the clock by hand; an idle reset between two slow tests would
# silently swap the world out from under them. The lifecycle rules have their
# own pure-function tests.
os.environ["AUTO_RESET_ENABLED"] = "false"

from app.database import SessionLocal, create_all  # noqa: E402
from app.seeding import reseed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    if TEST_DB.exists():
        TEST_DB.unlink()
    create_all()


@pytest.fixture
def db():
    """A session against a freshly reseeded baseline."""
    session = SessionLocal()
    try:
        reseed(session)
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db):
    """TestClient sharing the reseeded database (same SQLite file)."""
    from fastapi.testclient import TestClient

    from app.main import app

    # The app's lifespan would re-seed and start the background loops; the
    # fixture above already prepared the data, and both loops are disabled via
    # the environment set at the top of this file.
    with TestClient(app) as test_client:
        yield test_client
