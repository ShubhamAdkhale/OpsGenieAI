"""The new pipeline: weather, provenance, the priority summary and the tick.

These cover the parts of the rebuild that the demo-arc tests exercise only
incidentally: that weather failure is survivable and honestly labelled, that
the dashboard's headline decision is computed server-side, and that the
physics tick is the single place operational state changes.
"""

from __future__ import annotations

import pytest

from app.models import Inventory, Machine, Shipment, WeatherObservation
from app.providers.base import FetchContext
from app.providers.weather import open_meteo
from app.services import priority, provenance, weather
from app.simulation import engine, physics, scenarios


# ---------------------------------------------------------------------------
# Weather: classification, fallback and provenance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "temperature,precipitation,wind,code,expected",
    [
        (30.0, 0.0, 10.0, 0, "CLEAR"),
        (30.0, 3.0, 12.0, 63, "RAIN"),
        (30.0, 9.0, 20.0, 63, "STORM"),
        (30.0, 2.0, 30.0, 95, "STORM"),
        (30.0, 12.0, 65.0, 95, "EXTREME"),
        # Heat is a cold-chain event on its own, with no rain at all.
        (39.0, 0.0, 5.0, 0, "STORM"),
        (43.0, 0.0, 5.0, 0, "EXTREME"),
    ],
)
def test_weather_classification_is_transparent(
    temperature, precipitation, wind, code, expected
):
    assert weather.classify(temperature, precipitation, wind, code) == expected


def test_open_meteo_failure_falls_back_without_raising(monkeypatch):
    """The demo must survive an unreachable API, and say that it did."""

    def explode(*args, **kwargs):
        raise OSError("no network")

    monkeypatch.setattr(open_meteo.httpx, "get", explode)
    point = weather.Waypoint("Lonavala", 18.75, 73.40)
    assert open_meteo.PROVIDER.fetch([point], FetchContext()) == {}


def test_fallback_weather_is_deterministic_and_labelled():
    point = weather.Waypoint("Lonavala", 18.75, 73.40)
    first = weather.simulate(point, 6 * 60.0)
    again = weather.simulate(point, 6 * 60.0)
    assert first == again
    assert first["source"] == weather.FALLBACK
    # ...and it actually varies over the day, or the thermal model has nothing
    # to integrate against.
    assert weather.simulate(point, 15 * 60.0)["temperature_c"] > first["temperature_c"]


def test_a_simulated_reading_is_never_labelled_live(db):
    summary = provenance.weather_summary(db)
    assert summary["waypoints_total"] > 0
    for observation in summary["observations"]:
        if observation["source"] != weather.LIVE:
            assert observation["label"] == provenance.SIMULATED
    # Weather is off in tests, so nothing may claim to be live.
    assert summary["waypoints_live"] == 0
    assert summary["label"] == provenance.SIMULATED


def test_injected_weather_is_labelled_injected_not_live(db):
    engine.trigger_event(db, "weather_deterioration")
    route = db.query(Shipment).filter(Shipment.is_hero.is_(True)).one().routes[0]
    state = physics.environment(db)
    _, _, level, source = physics.ambient_for_route(db, route, state)
    assert source == weather.INJECTED
    assert level in {"STORM", "EXTREME"}


def test_an_active_injection_downgrades_the_weather_label(db):
    """A scenario offset is applied when ambient is READ, not when it is stored.

    So the stored rows stay genuinely live while the temperature the thermal
    model sees is not. Reporting LIVE in that state would be the exact false
    claim the provenance module exists to prevent.
    """
    engine.trigger_event(db, "weather_deterioration")
    summary = provenance.weather_summary(db)
    assert summary["offset_active"] is True
    assert summary["ambient_offset_c"] > 0
    assert summary["label"] == "MIXED"

    detail = next(s for s in provenance.streams(db) if s["name"] == "Weather")["detail"]
    assert "NOT the observed one" in detail


def test_provenance_lists_every_stream_with_a_valid_label(db):
    for stream in provenance.streams(db):
        assert stream["label"] in {
            provenance.LIVE,
            provenance.SIMULATED,
            provenance.PREDICTED,
            "MIXED",
        }
        assert stream["detail"]
    names = {s["name"] for s in provenance.streams(db)}
    assert {"Weather", "IoT sensors", "Melt Index & spoilage"} <= names


def test_weather_actually_influences_the_risk_score(db):
    """The link the brief asks for, isolated from every other cause.

    Nothing changes here except ambient temperature. If the Melt Index does not
    move, weather is decorative.
    """
    hero = db.query(Shipment).filter(Shipment.is_hero.is_(True)).one()
    for _ in range(6):
        physics.tick(db)
    db.refresh(hero)
    baseline_melt = hero.melt_index
    baseline_cargo = hero.cargo_temperature_c

    state = physics.environment(db)
    state.weather_mode = "HEAT_STORM"
    state.ambient_offset_c = 14.0
    db.flush()
    for _ in range(6):
        physics.tick(db)
    db.refresh(hero)

    assert hero.cargo_temperature_c > baseline_cargo, "hotter ambient did not warm the cargo"
    assert hero.melt_index > baseline_melt, "warmer cargo did not raise the risk score"


# ---------------------------------------------------------------------------
# The tick is the only thing that moves operational state
# ---------------------------------------------------------------------------


def test_route_delay_is_always_the_sum_of_its_causes(db):
    engine.trigger_event(db, "traffic_incident")
    for route in db.query(Shipment).filter(Shipment.is_hero.is_(True)).one().routes:
        assert route.delay_minutes == pytest.approx(
            route.incident_delay_minutes
            + route.congestion_delay_minutes
            + route.weather_delay_minutes,
            abs=0.05,
        )


def test_incidents_clear_on_their_own(db):
    engine.trigger_event(db, "traffic_incident")
    route = next(
        r
        for r in db.query(Shipment).filter(Shipment.is_hero.is_(True)).one().routes
        if r.is_selected
    )
    peak = route.incident_delay_minutes
    assert peak > 0
    for _ in range(20):
        physics.tick(db)
    db.refresh(route)
    assert route.incident_delay_minutes < peak


def test_an_injected_weather_front_passes(db):
    engine.trigger_event(db, "weather_deterioration")
    assert physics.environment(db).ambient_offset_c > 0
    for _ in range(200):
        physics.tick(db)
    state = physics.environment(db)
    assert state.ambient_offset_c == 0.0
    assert state.weather_mode == "AUTO"


def test_inventory_is_drawn_down_by_demand(db):
    before = {row.id: row.current_stock for row in db.query(Inventory).all()}
    for _ in range(30):
        physics.tick(db)
    after = {row.id: row.current_stock for row in db.query(Inventory).all()}
    assert any(after[key] < before[key] for key in before), "stock never moved"
    assert all(value >= 0 for value in after.values())


def test_machines_accumulate_runtime_and_wear(db):
    machine = db.query(Machine).filter(Machine.code == "RF-207").one()
    hours_before = machine.operating_hours
    efficiency_before = machine.cooling_efficiency
    for _ in range(40):
        physics.tick(db)
    db.refresh(machine)
    assert machine.operating_hours > hours_before
    # Normal wear is slow but real, and health tracks efficiency exactly.
    assert machine.cooling_efficiency <= efficiency_before
    assert machine.status in {"HEALTHY", "WARNING", "CRITICAL"}


def test_the_audit_trail_does_not_grow_without_bound(db):
    """A live tick writes rows every few seconds; it must prune after itself."""
    from app.models import RiskAssessment, SensorReading

    for _ in range(120):
        physics.tick(db)
    for shipment in db.query(Shipment).all():
        count = (
            db.query(RiskAssessment)
            .filter(RiskAssessment.shipment_id == shipment.id)
            .count()
        )
        assert count <= physics.MAX_ASSESSMENTS_PER_SHIPMENT + 1
    for machine in db.query(Machine).all():
        count = db.query(SensorReading).filter(SensorReading.machine_id == machine.id).count()
        assert count <= physics.MAX_READINGS_PER_MACHINE + 1


# ---------------------------------------------------------------------------
# The priority summary
# ---------------------------------------------------------------------------


def test_priority_summary_picks_the_largest_exposure(db):
    """Ranking rule: the decision whose delay costs the most money.

    At baseline that is NOT the hero shipment - the seeded board carries a
    couple of genuinely exposed loads - and that is the correct answer. The
    hero only takes the top slot once the demo escalates it past them.
    """
    summary = priority.summarize(db)
    assert summary["state"] == "ATTENTION"

    worst = max(
        (s for s in db.query(Shipment).all() if s.status != "REROUTED"),
        key=lambda s: s.expected_loss_inr,
    )
    assert summary["subject"]["code"] == worst.code
    assert summary["financial"]["expected_loss_inr"] == worst.expected_loss_inr


def test_priority_summary_is_calm_when_nothing_is_exposed(db, monkeypatch):
    """The honest empty state: no invented crisis when the board is quiet."""
    monkeypatch.setattr(priority, "ATTENTION_EXPECTED_LOSS_INR", 10_000_000.0)
    summary = priority.summarize(db)
    assert summary["state"] == "NORMAL"
    assert summary["severity"] == "NORMAL"
    assert summary["subject"] is None
    assert summary["answers"]["what_to_do"] == "Monitor."


def test_the_hero_takes_over_the_top_slot_as_it_escalates(db):
    before = priority.summarize(db)["subject"]["code"]
    for event in scenarios.ESCALATION_SEQUENCE:
        engine.trigger_event(db, event)
    after = priority.summarize(db)["subject"]["code"]
    assert before != "SC-1042"
    assert after == "SC-1042"


def test_priority_summary_answers_all_five_questions(db):
    for event in scenarios.ESCALATION_SEQUENCE:
        engine.trigger_event(db, event)
    summary = priority.summarize(db)

    assert summary["state"] == "ATTENTION"
    assert summary["severity"] == "CRITICAL"
    assert summary["subject"]["code"] == "SC-1042"

    answers = summary["answers"]
    assert set(answers) == {
        "what_is_wrong",
        "what_will_happen",
        "why",
        "what_to_do",
        "how_much_at_risk",
    }
    assert all(value for value in answers.values()), answers

    # The rupee arithmetic is spelled out by the backend, not the browser.
    financial = summary["financial"]
    assert financial["expected_loss_inr"] == pytest.approx(
        financial["shipment_value_inr"] * summary["prediction"]["probability"], rel=0.02
    )
    assert " x " in financial["working"]
    assert financial["loss_avoided_inr"] > 0

    # WHY is attributed to real weighted components.
    assert summary["causes"]
    assert summary["cause_summary"]
    # ...and the equipment story is folded in rather than shown as a rival card.
    assert summary["equipment"]["code"] == "RF-204"


def test_priority_summary_surfaces_the_gated_action(db):
    for event in scenarios.ESCALATION_SEQUENCE:
        engine.trigger_event(db, event)
    recommendation = priority.summarize(db)["recommendation"]

    assert recommendation["type"] == "REROUTE"
    assert recommendation["requires_approval"] is True
    assert recommendation["workflow_id"] is not None
    assert recommendation["gate_reason"]


def test_dashboard_serves_the_summary_and_provenance(client):
    body = client.get("/api/dashboard").json()
    assert "priority" in body
    assert "provenance" in body
    assert "environment" in body
    assert body["environment"]["sim_minutes_per_tick"] > 0
    assert body["provenance"]["streams"]


def test_environment_endpoint_reports_the_clock(client):
    body = client.get("/api/simulation/environment").json()
    assert body["tick_count"] >= 0
    assert body["physics"]["enabled"] is False  # disabled under test
    assert body["provenance"]["weather"]["waypoints_live"] == 0


def test_manual_tick_endpoint_advances_the_world(client):
    before = client.get("/api/simulation/environment").json()["sim_minutes"]
    client.post("/api/simulation/tick", json={})
    after = client.get("/api/simulation/environment").json()["sim_minutes"]
    assert after > before


# ---------------------------------------------------------------------------
# Alerts: one per state, not one per tick
# ---------------------------------------------------------------------------


def test_alerts_dedupe_on_state_not_on_message_text(db):
    """A live tick must not turn the alert feed into a scrolling log.

    The alert messages embed figures that the physics tick recomputes every few
    seconds, so text-matched deduplication never matched and a shipment sitting
    in one risk band produced a fresh alert on every tick. Keying on the state
    means one alert per (asset, band), with its message refreshed in place.
    """
    from app.models import Alert

    for event in scenarios.ESCALATION_SEQUENCE:
        engine.trigger_event(db, event)
    settled = db.query(Alert).count()

    for _ in range(60):
        physics.tick(db)
    after = db.query(Alert).count()

    # A handful of genuine band changes are fine; sixty ticks of noise are not.
    assert after - settled <= 4, f"{after - settled} alerts added by 60 idle ticks"

    keys = [row.dedupe_key for row in db.query(Alert).all()]
    assert len(keys) == len(set(keys)), "duplicate dedupe keys in the feed"


def test_a_band_change_does_raise_a_new_alert(db):
    """...but dedupe must not silence real escalation."""
    from app.models import Alert

    engine.trigger_event(db, "traffic_incident")
    before = {row.dedupe_key for row in db.query(Alert).all()}
    engine.trigger_event(db, "refrigeration_degradation")
    engine.trigger_event(db, "weather_deterioration")
    after = {row.dedupe_key for row in db.query(Alert).all()}

    new_hero_alerts = {k for k in after - before if "SC-1042" in k}
    assert new_hero_alerts, "escalating the hero raised no new alert"


def test_the_alert_feed_is_pruned(db):
    from app.models import Alert
    from app.services import alerts as alert_service

    for _ in range(alert_service.MAX_ALERTS + 40):
        alert_service.raise_alert(
            db, "INFO", "filler", related_type="system", dedupe_key=f"filler-{_}"
        )
    db.flush()
    alert_service.prune(db)
    assert db.query(Alert).count() <= alert_service.MAX_ALERTS
