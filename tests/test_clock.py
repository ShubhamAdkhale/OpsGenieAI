"""One clock: every simulated record is stamped in twin time, and says its timezone."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.api.serializers import iso
from app.models import Alert, SensorReading
from app.simulation import clock, engine, physics


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def test_an_episode_opens_at_six_in_the_morning_ist(db):
    engine.reset(db)
    twin = clock.now().astimezone(clock.IST)
    assert (twin.hour, twin.minute) == (6, 0)


def test_records_written_by_a_tick_carry_the_twin_moment_they_happened(db):
    engine.reset(db)
    for _ in range(4):
        physics.tick(db)
    state = physics.environment(db)
    newest = db.query(SensorReading).order_by(SensorReading.id.desc()).first()
    expected = clock.at(state.sim_minutes)
    assert abs(_aware(newest.timestamp) - expected) < timedelta(seconds=1)


def test_seeded_history_ends_at_the_start_of_the_episode_not_the_wall_clock(db):
    engine.reset(db)
    start = clock.now()
    latest_alert = db.query(Alert).order_by(Alert.id.desc()).first()
    assert abs(_aware(latest_alert.created_at) - start) < timedelta(seconds=1)


def test_every_timestamp_is_serialised_with_an_offset():
    # A bare "2026-09-24T06:00:00" is read as LOCAL time by the browser.
    naive = datetime(2026, 9, 24, 0, 30)
    assert iso(naive).endswith("+00:00")
    assert iso(None) is None


def test_the_dashboard_reports_twin_time(client):
    body = client.get("/api/dashboard").json()
    twin = datetime.fromisoformat(body["environment"]["twin_time"]).astimezone(clock.IST)
    assert f"{twin.hour:02d}:{twin.minute:02d}" == body["environment"]["sim_clock"]
