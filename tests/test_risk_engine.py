"""Unit tests for the Melt Index formula and the route optimizer (§31 phases 5-6)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import risk_engine


def _shipment(**kwargs) -> SimpleNamespace:
    defaults = dict(
        minutes_outside_safe_range=0.0,
        remaining_shelf_life_hours=24.0,
        shipment_value_inr=100_000.0,
        machine=None,
        routes=[],
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _product(shelf_hours: float = 24.0) -> SimpleNamespace:
    return SimpleNamespace(unit_shelf_life_hours=shelf_hours)


def _route(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id=1,
        label="Test route",
        eta_minutes=60.0,
        delay_minutes=0.0,
        traffic_level="LOW",
        weather_level="CLEAR",
        is_current=True,
        is_selected=True,
        reefer_health_override=None,
        notes="",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_weights_sum_to_one():
    """If the weights ever stop summing to 1, the 0-100 scale is a lie."""
    assert sum(risk_engine.WEIGHTS.values()) == pytest.approx(1.0)


def test_all_inputs_nominal_gives_zero_risk():
    shipment = _shipment(
        minutes_outside_safe_range=0.0,
        remaining_shelf_life_hours=24.0,
        machine=SimpleNamespace(
            health_score=100.0, cooling_efficiency=95.0,
            baseline_cooling_efficiency=95.0, code="RF-999",
        ),
    )
    components = risk_engine.compute_components(shipment, _product(), _route())
    assert components.melt_index == pytest.approx(0.0)
    assert risk_engine.band_for(components.melt_index) == "SAFE"


def test_each_component_is_scaled_to_0_100():
    """A single maxed-out component must contribute exactly its own weight."""
    # Weather EXTREME = 100 (§18 lookup), weight 0.15 -> 15 points.
    shipment = _shipment(remaining_shelf_life_hours=24.0)
    components = risk_engine.compute_components(
        shipment, _product(), _route(weather_level="EXTREME")
    )
    assert components.weather_risk == 100.0
    assert components.melt_index == pytest.approx(15.0)


def test_traffic_risk_clamps_at_one_hour_of_delay():
    shipment = _shipment(remaining_shelf_life_hours=48.0)
    components = risk_engine.compute_components(
        shipment, _product(48.0), _route(delay_minutes=180.0)
    )
    assert components.traffic_risk == 100.0  # clamped, not 300


def test_refrigeration_risk_is_inverse_of_machine_health():
    machine = SimpleNamespace(
        health_score=23.0, cooling_efficiency=67.82,
        baseline_cooling_efficiency=85.82, code="RF-204",
    )
    shipment = _shipment(machine=machine, remaining_shelf_life_hours=24.0)
    components = risk_engine.compute_components(shipment, _product(), _route())
    assert components.refrigeration_risk == pytest.approx(77.0)
    # §24 reports the drop against the unit's own dispatch baseline.
    assert components.cooling_efficiency_drop == pytest.approx(18.0, abs=0.01)


def test_route_reefer_override_replaces_machine_health():
    """A route that swaps the load onto a standby unit carries that unit's risk."""
    machine = SimpleNamespace(
        health_score=23.0, cooling_efficiency=67.8,
        baseline_cooling_efficiency=85.8, code="RF-204",
    )
    shipment = _shipment(machine=machine, remaining_shelf_life_hours=24.0)
    on_failing_unit = risk_engine.compute_components(shipment, _product(), _route())
    on_standby = risk_engine.compute_components(
        shipment, _product(), _route(reefer_health_override=88.0)
    )
    assert on_standby.refrigeration_risk == pytest.approx(12.0)
    assert on_standby.melt_index < on_failing_unit.melt_index


def test_eta_risk_is_100_when_arrival_misses_the_window():
    shipment = _shipment(remaining_shelf_life_hours=2.0)
    components = risk_engine.compute_components(
        shipment, _product(), _route(eta_minutes=240.0)
    )
    assert components.eta_risk == 100.0
    assert components.eta_margin_hours < 0


def test_band_boundaries_match_spec():
    for value, expected in [
        (0, "SAFE"), (20, "SAFE"), (21, "LOW"), (40, "LOW"),
        (41, "MODERATE"), (60, "MODERATE"), (61, "HIGH"), (80, "HIGH"),
        (81, "CRITICAL"), (100, "CRITICAL"),
    ]:
        assert risk_engine.band_for(value) == expected, value


def test_band_uses_the_displayed_rounded_value():
    """20.4 displays as 20, so it must badge as SAFE, not LOW."""
    assert risk_engine.band_for(20.4) == "SAFE"
    assert risk_engine.band_for(20.6) == "LOW"


def test_spoilage_curve_is_monotone_and_calibrated():
    curve = risk_engine.spoilage_from_melt_index
    values = [curve(m) for m in range(0, 101, 5)]
    assert values == sorted(values)
    assert 0.0 < values[0] < 0.05
    # The curve deliberately never saturates at 1.0: even a Melt Index of 100
    # means "very likely to spoil", not "certain to spoil".
    assert 0.85 < values[-1] < 0.95
    # The two calibration anchors the §7 rupee figures depend on.
    assert curve(88.71) == pytest.approx(0.82, abs=0.005)
    assert curve(38.52) == pytest.approx(0.21, abs=0.005)


def test_expected_loss_is_value_times_probability():
    shipment = _shipment(shipment_value_inr=500_000.0)
    assert risk_engine.expected_loss(shipment, 0.82) == 410_000.0


def test_optimizer_prefers_lower_expected_loss_over_faster_eta(db):
    """§20 / §7: Route B wins despite a LONGER nominal ETA, because its
    expected loss is lower. This is the whole point of the optimizer."""
    from app.models import Shipment

    shipment = db.query(Shipment).filter(Shipment.code == "SC-1042").one()
    # Put the shipment into the degraded end-state of the scripted arc.
    shipment.machine.health_score = 23.0
    shipment.minutes_outside_safe_range = 121.0
    shipment.remaining_shelf_life_hours = 3.5
    route_a = next(r for r in shipment.routes if r.is_selected)
    route_a.delay_minutes = 100.0
    route_a.weather_level = "STORM"
    db.flush()

    result = risk_engine.optimize(shipment)
    route_b = next(e for e in result.evaluations if not e.route.is_selected)
    current = result.current

    assert result.recommended.route.id == route_b.route.id
    # Route B is slower on paper...
    assert route_b.route.eta_minutes > route_a.eta_minutes
    # ...but arrives sooner once Route A's delay counts, and loses far less.
    assert route_b.expected_loss_inr < current.expected_loss_inr
    assert result.should_reroute


def test_optimizer_flags_when_no_route_meets_the_shelf_life_window(db):
    from app.models import Shipment

    shipment = db.query(Shipment).filter(Shipment.code == "SC-1042").one()
    shipment.remaining_shelf_life_hours = 0.2  # nothing can arrive in 12 minutes
    db.flush()
    result = risk_engine.optimize(shipment)
    assert result.no_safe_option
    # It still recommends something — the least-bad option (§20).
    assert result.recommended is not None
