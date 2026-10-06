"""The end-to-end demo test.

This file used to assert hardcoded figures (Melt Index 18 / 36 / 64 / 89,
expected loss exactly Rs 4,10,000). Those assertions were only meaningful while
the simulator applied tuned deltas chosen to produce them - they tested that
the script still said what the script said.

The simulator is now causal: events perturb a root cause and the physics tick
integrates forward, so the exact figures depend on the model rather than on a
table of target values. This file therefore asserts the properties that
actually matter, and which a broken pipeline could not satisfy:

  * each escalation moves the Melt Index UP, and the climax is CRITICAL
  * the excursion figure is EARNED - cargo temperature really breaches the
    product's safe threshold before a single excursion minute is counted
  * degrading a MACHINE moves a SHIPMENT's risk (the cross-module link)
  * the anomaly detector fires on genuine drift, with no outlier injected
  * the recommended lane is the one with lower EXPECTED LOSS, not lower ETA
  * a high-impact action stops for a human
  * approval reduces risk, and repair reduces it again, with nobody assigning
    a lower number anywhere
  * the whole arc is still reproducible three times running

Reproducibility survives because the clock is simulated: N ticks of
integration from the same baseline always produce the same state.
"""

from __future__ import annotations

import pytest

from app.models import Machine, Shipment, Workflow
from app.seed_config import (
    BASELINE_DEGRADATION_RATE,
    DEMO_ARC_MIN_ESCALATION,
    DEMO_EVENTS,
    HERO_SHIPMENT_CODE,
    SHIPMENTS,
)
from app.services import decision_engine, risk_engine
from app.simulation import engine, physics, scenarios

HERO_SPEC = next(s for s in SHIPMENTS if s["code"] == HERO_SHIPMENT_CODE)


def _hero(db) -> Shipment:
    return db.query(Shipment).filter(Shipment.code == "SC-1042").one()


def _reefer(db) -> Machine:
    return db.query(Machine).filter(Machine.code == "RF-204").one()


def _run_escalations(db) -> None:
    for event_type in scenarios.ESCALATION_SEQUENCE:
        engine.trigger_event(db, event_type)


# ---------------------------------------------------------------------------
# The scenarios must not be able to state a consequence
# ---------------------------------------------------------------------------


def test_no_scenario_can_assign_a_consequence():
    """The structural guarantee behind every other test in this file.

    If a scenario could set a Melt Index, an excursion figure or a spoilage
    probability, the pipeline would be decorative. The vocabulary of a scenario
    is restricted to root causes, and this test pins that down.
    """
    forbidden = {
        "expected_melt_index",
        "melt_index",
        "minutes_outside_delta",
        "minutes_outside_safe_range",
        "shelf_life_delta_hours",
        "spoilage_probability",
        "expected_loss_inr",
        "health_delta",
        "delay_minutes",
    }
    for event_type, spec in DEMO_EVENTS.items():
        overlap = forbidden.intersection(spec)
        assert not overlap, f"scenario '{event_type}' assigns consequences: {overlap}"
        assert spec["cause"] in scenarios.CAUSES, f"'{event_type}' names an unknown cause"


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def test_baseline_is_safe_and_holding_its_setpoint(db):
    hero = _hero(db)
    assert hero.status == "SAFE"
    assert hero.melt_index < 20
    assert hero.machine.code == "RF-204"
    assert hero.shipment_value_inr == 500_000.0
    # Dispatched at the setpoint, six degrees under the product's safe maximum.
    assert hero.cargo_temperature_c == pytest.approx(
        hero.product.safe_transit_temp_c - physics.SETPOINT_MARGIN_C
    )


def test_baseline_creates_no_workflow_for_the_hero(db):
    hero = _hero(db)
    assert db.query(Workflow).filter(Workflow.related_shipment_id == hero.id).count() == 0
    assert hero.status != "REROUTED"


def test_a_healthy_world_stays_calm_when_time_passes(db):
    """The simulation must not manufacture a crisis out of nothing.

    Twenty ticks with no event: a healthy reefer holds its setpoint, so no
    excursion accrues and the shipment stays out of the risk bands. Without
    this, "the numbers move" would be indistinguishable from "the numbers
    wander".
    """
    hero = _hero(db)
    excursion_before = hero.minutes_outside_safe_range
    for _ in range(20):
        physics.tick(db)
    db.refresh(hero)

    assert hero.cargo_temperature_c <= hero.product.safe_transit_temp_c
    assert hero.minutes_outside_safe_range == excursion_before
    assert hero.status in {"SAFE", "LOW"}


def test_time_passing_does_advance_the_world(db):
    """...but it is not frozen either. The clock and the sensors move."""
    state_before = physics.environment(db).sim_minutes
    reefer = _reefer(db)
    hours_before = reefer.operating_hours
    readings_before = len(reefer.readings)

    for _ in range(10):
        physics.tick(db)
    db.refresh(reefer)

    assert physics.environment(db).sim_minutes > state_before
    assert reefer.operating_hours > hours_before
    assert len(reefer.readings) > readings_before


# ---------------------------------------------------------------------------
# The escalation arc
# ---------------------------------------------------------------------------


def test_each_escalation_raises_the_melt_index(db):
    hero = _hero(db)
    previous = hero.melt_index
    trace = [previous]

    for event_type in scenarios.ESCALATION_SEQUENCE:
        engine.trigger_event(db, event_type)
        db.refresh(hero)
        assert hero.melt_index >= previous + DEMO_ARC_MIN_ESCALATION, (
            f"'{event_type}' moved the Melt Index from {previous:.1f} to "
            f"{hero.melt_index:.1f}, less than the {DEMO_ARC_MIN_ESCALATION} "
            "points an escalation is expected to add"
        )
        previous = hero.melt_index
        trace.append(previous)

    assert hero.status == "CRITICAL", f"arc ended at {hero.status}, trace={trace}"


def test_the_traffic_incident_only_touches_delay(db):
    """Step 1 changes an input. It must not reach past the route."""
    hero = _hero(db)
    excursion_before = hero.minutes_outside_safe_range
    route = risk_engine.selected_route(hero)
    delay_before = route.delay_minutes

    engine.trigger_event(db, "traffic_incident")
    db.refresh(hero)
    route = risk_engine.selected_route(hero)

    assert route.incident_delay_minutes > 0
    assert route.delay_minutes > delay_before
    # delay_minutes is always the sum of its three causes, never assigned.
    assert route.delay_minutes == pytest.approx(
        route.incident_delay_minutes
        + route.congestion_delay_minutes
        + route.weather_delay_minutes,
        abs=0.05,
    )
    # The cargo was still cold, so no excursion was invented to make the
    # Melt Index move. The ETA margin did the work instead.
    assert hero.minutes_outside_safe_range == excursion_before
    assert hero.melt_index > 20


def test_degradation_is_a_wear_rate_not_a_health_assignment(db):
    reefer = _reefer(db)
    assert reefer.degradation_rate_per_hour == BASELINE_DEGRADATION_RATE
    efficiency_before = reefer.cooling_efficiency

    engine.trigger_event(db, "refrigeration_degradation")
    db.refresh(reefer)

    assert reefer.degradation_rate_per_hour > BASELINE_DEGRADATION_RATE
    # Efficiency fell because the rate was integrated over the settle window,
    # so the loss should be about rate x hours rather than a round number.
    settle_hours = DEMO_EVENTS["refrigeration_degradation"]["settle_minutes"] / 60.0
    expected_loss = DEMO_EVENTS["refrigeration_degradation"]["amount"] * settle_hours
    assert efficiency_before - reefer.cooling_efficiency == pytest.approx(
        expected_loss, rel=0.35
    )
    # Health is a pure function of efficiency, so the two cannot disagree.
    assert reefer.health_score < 74.0


def test_anomaly_is_detected_from_genuine_drift(db):
    """No outlier is injected anywhere. Sensor values are generated FROM the
    efficiency every tick, so the IsolationForest sees a real trajectory."""
    reefer = _reefer(db)
    engine.trigger_event(db, "refrigeration_degradation")
    db.refresh(reefer)

    assert reefer.anomaly_detected, f"anomaly score was only {reefer.anomaly_score}"
    assert reefer.failure_probability > 0.75  # the action threshold
    assert reefer.status in {"WARNING", "CRITICAL"}


def test_degradation_raises_a_maintenance_workflow_naming_the_shipment(db):
    engine.trigger_event(db, "refrigeration_degradation")
    reefer = _reefer(db)
    workflow = (
        db.query(Workflow)
        .filter(
            Workflow.workflow_type == "MAINTENANCE",
            Workflow.related_machine_id == reefer.id,
        )
        .order_by(Workflow.id.desc())
        .first()
    )
    assert workflow is not None
    assert workflow.status == "PENDING_APPROVAL"
    assert "RF-204" in workflow.trigger_reason
    assert "SC-1042" in workflow.trigger_reason  # the cross-module link


def test_the_cross_module_link_is_real(db):
    """Predictive maintenance must move operations.

    Degrading the MACHINE raises the SHIPMENT's refrigeration risk, and it does
    so through cooling power in the thermal model, not through a shipment-level
    delta applied by the event.
    """
    hero = _hero(db)
    before = hero.melt_index
    engine.trigger_event(db, "refrigeration_degradation")
    db.refresh(hero)

    assert hero.melt_index > before
    latest = risk_engine.latest_assessment(db, hero.id)
    assert latest.machine_code == "RF-204"
    assert latest.refrigeration_risk > 100.0 - 74.0  # worse than the seeded health


def test_the_cold_chain_breach_is_earned_by_the_thermal_model(db):
    """The claim this whole rebuild rests on.

    Excursion minutes accrue only while cargo temperature is genuinely above
    the product's safe maximum. Heat and degradation together push it over;
    neither the event nor the risk engine ever writes the figure.
    """
    hero = _hero(db)
    safe_max = hero.product.safe_transit_temp_c
    excursion_at_start = hero.minutes_outside_safe_range

    engine.trigger_event(db, "traffic_incident")
    engine.trigger_event(db, "refrigeration_degradation")
    db.refresh(hero)
    # Still cold: the reefer is losing efficiency but has not lost the race yet.
    assert hero.cargo_temperature_c < safe_max
    assert hero.minutes_outside_safe_range == excursion_at_start

    engine.trigger_event(db, "weather_deterioration")
    db.refresh(hero)
    # Now ambient has climbed and cooling power has fallen far enough that heat
    # ingress wins, so the box warms past the threshold and the counter runs.
    assert hero.cargo_temperature_c > safe_max
    assert hero.minutes_outside_safe_range > excursion_at_start
    # Q10: warm cargo ages faster than the clock.
    assert hero.remaining_shelf_life_hours < 16.0


def test_shelf_life_burns_faster_once_the_cargo_is_warm(db):
    hero = _hero(db)
    _run_escalations(db)
    db.refresh(hero)
    assert hero.cargo_temperature_c > hero.product.safe_transit_temp_c

    shelf_before = hero.remaining_shelf_life_hours
    ticks = 10
    for _ in range(ticks):
        physics.tick(db)
    db.refresh(hero)

    elapsed_hours = ticks * physics.settings.sim_minutes_per_tick / 60.0
    burned = shelf_before - hero.remaining_shelf_life_hours
    assert burned > elapsed_hours, (
        f"warm cargo burned {burned:.2f}h of shelf life over {elapsed_hours:.2f}h "
        "of transit; the Q10 term is not doing its job"
    )


# ---------------------------------------------------------------------------
# Optimization, gating and recovery
# ---------------------------------------------------------------------------


def test_the_optimizer_prefers_expected_loss_over_eta(db):
    hero = _hero(db)
    _run_escalations(db)
    result = risk_engine.optimize(hero)

    assert result.recommended.route.label.startswith("Route B")
    assert result.recommended.expected_loss_inr < result.current.expected_loss_inr
    assert result.loss_avoided_inr > 0
    # The recommendation is justified by risk, not by speed: Route B carries a
    # far lower spoilage probability because it transfers to a healthy reefer.
    assert result.recommended.spoilage_probability < result.current.spoilage_probability / 2


def test_a_high_impact_action_waits_for_a_human(db):
    hero = _hero(db)
    _run_escalations(db)

    workflow = decision_engine.open_workflow(db, "REROUTE", shipment_id=hero.id)
    assert workflow is not None
    assert workflow.impact_inr > decision_engine.IMPACT_MEDIUM_CEILING
    assert workflow.status == "PENDING_APPROVAL"
    assert "Route B" in workflow.recommendation_text


def test_approval_reroutes_and_the_risk_falls(db):
    hero = _hero(db)
    _run_escalations(db)
    db.refresh(hero)
    melt_before = hero.melt_index
    loss_before = hero.expected_loss_inr

    workflow = decision_engine.open_workflow(db, "REROUTE", shipment_id=hero.id)
    expected_avoided = workflow.impact_inr
    decision_engine.approve(db, workflow)
    db.commit()
    db.refresh(hero)

    assert hero.status == "REROUTED"
    assert hero.melt_index < melt_before
    assert hero.expected_loss_inr < loss_before
    assert hero.loss_avoided_inr == expected_avoided
    assert next(r for r in hero.routes if r.is_selected).label.startswith("Route B")


def test_repair_restores_the_wear_rate_and_the_efficiency(db):
    reefer = _reefer(db)
    engine.trigger_event(db, "refrigeration_degradation")
    db.refresh(reefer)
    assert reefer.degradation_rate_per_hour > BASELINE_DEGRADATION_RATE
    degraded_efficiency = reefer.cooling_efficiency

    engine.trigger_event(db, "maintenance_completed")
    db.refresh(reefer)

    assert reefer.degradation_rate_per_hour == BASELINE_DEGRADATION_RATE
    assert reefer.cooling_efficiency > degraded_efficiency
    assert reefer.cooling_efficiency == pytest.approx(
        reefer.baseline_cooling_efficiency, abs=0.5
    )


def test_repairing_the_reefer_cools_the_cargo_again(db):
    """Recovery is as causal as escalation: nobody lowers the risk by hand."""
    hero = _hero(db)
    _run_escalations(db)
    db.refresh(hero)
    warm = hero.cargo_temperature_c
    assert warm > hero.product.safe_transit_temp_c

    engine.trigger_event(db, "maintenance_completed")
    db.refresh(hero)
    assert hero.cargo_temperature_c < warm


# ---------------------------------------------------------------------------
# Reset and reproducibility
# ---------------------------------------------------------------------------


def test_reset_restores_the_baseline(db):
    _run_escalations(db)
    assert _hero(db).status == "CRITICAL"

    engine.reset(db)
    hero = _hero(db)
    assert hero.status == "SAFE"
    assert hero.minutes_outside_safe_range == HERO_SPEC["minutes_outside_safe_range"]
    assert hero.remaining_shelf_life_hours == HERO_SPEC["remaining_shelf_life_hours"]
    assert hero.cargo_temperature_c == pytest.approx(
        hero.product.safe_transit_temp_c - physics.SETPOINT_MARGIN_C
    )
    reefer = _reefer(db)
    assert reefer.health_score == 74.0
    assert reefer.degradation_rate_per_hour == BASELINE_DEGRADATION_RATE
    assert physics.environment(db).ambient_offset_c == 0.0


def test_arc_is_identical_three_times_in_a_row(db):
    """Causal does not mean unrepeatable.

    Because the clock is simulated rather than read from the wall, and the
    weather fallback is a deterministic function of that clock, the same
    sequence of triggers integrates to the same state every time.
    """
    runs = []
    for _ in range(3):
        engine.reset(db)
        trace = [round(_hero(db).melt_index, 2)]
        for event_type in scenarios.ESCALATION_SEQUENCE:
            engine.trigger_event(db, event_type)
            trace.append(round(_hero(db).melt_index, 2))
        hero = _hero(db)
        runs.append(
            (
                tuple(trace),
                hero.status,
                hero.expected_loss_inr,
                round(hero.cargo_temperature_c, 2),
                round(hero.minutes_outside_safe_range, 2),
            )
        )

    assert runs[0] == runs[1] == runs[2], f"runs diverged: {runs}"
    # And the arc really is an escalation, not a flat line.
    trace = runs[0][0]
    assert trace == tuple(sorted(trace))
    assert trace[-1] > 80


def test_unknown_event_type_is_rejected(db):
    with pytest.raises(engine.SimulationError):
        engine.trigger_event(db, "alien_invasion")
