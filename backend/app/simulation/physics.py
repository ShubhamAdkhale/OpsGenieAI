"""The causal simulation core.

This module replaces the old "apply a tuned delta and hope the number lands"
approach. Nothing here assigns a Melt Index, a spoilage probability or an
excursion figure. It integrates a small set of transparent physical and
operational relationships forward in simulated time, and every downstream
number is then *derived* by `risk_engine` from the state this produced.

The chain, end to end:

    ambient weather (Open-Meteo or labelled fallback)
      + reefer cooling power (efficiency, itself integrated from a wear rate)
        -> cargo temperature            (Newton's law of cooling)
        -> minutes outside safe range   (accumulated only while genuinely warm)
        -> shelf life burn rate         (Q10 rule: warm cargo ages faster)
    traffic congestion + incidents + weather
        -> route delay -> ETA -> ETA margin
    all of the above
        -> risk_engine.recalculate -> spoilage -> expected loss -> decision

Time advances by a FIXED step per tick (`sim_minutes_per_tick`) rather than
from the wall clock. That is what keeps the demo repeatable without scripting
it: N ticks of integration always produce the same state from the same start.
"""

from __future__ import annotations

import logging
import math
import random

from sqlalchemy.orm import Session

from app.config import settings
from app.ml.synthetic import (
    EFFICIENCY_FLOOR,
    NOMINAL_EFFICIENCY,
    health_for_efficiency,
    sensors_for_efficiency,
)
from app.models import (
    DELIVERED,
    EnvironmentState,
    Inventory,
    Machine,
    Product,
    RiskAssessment,
    Route,
    SensorReading,
    Shipment,
)
from app.services import alerts, risk_engine, weather
from app.simulation import clock

log = logging.getLogger("opsgenie.physics")

# ---------------------------------------------------------------------------
# Thermal model constants. These are the tuning knobs; they are named, they are
# few, and each one is a physical quantity someone can argue with.
# ---------------------------------------------------------------------------

# Box thermal conductance: fraction of the ambient/cargo temperature gap that
# leaks through the insulation per hour. 0.30 gives the box a ~3.3 hour thermal
# time constant, which is fast enough to watch inside a demo and slow enough to
# still look like a refrigerated trailer rather than a picnic bag.
BOX_CONDUCTANCE_PER_HOUR = 0.30

# Cooling capacity of a reefer at 100% efficiency, in degrees per hour of
# pull-down.
#
# The RATIO of these two constants is what actually matters, because it sets
# the equilibrium the box settles at:
#
#     T_equilibrium = T_ambient - (MAX_COOLING / CONDUCTANCE) x efficiency
#                   = T_ambient - 64 x efficiency
#
# So a healthy unit (86% efficiency) sits 55 C below ambient and holds any
# frozen setpoint easily, while the same unit at 70% sits only 45 C below and
# starts losing the cold chain once ambient climbs. Neither number was chosen
# to make a demo land; the crossover falls out of the ratio.
MAX_COOLING_C_PER_HOUR = 19.2

# Setpoint offset: reefers are set this far BELOW the product's safe maximum,
# so a healthy unit holds a margin and a degraded one eats into it first.
# 3 C puts every product on a real-world setpoint: frozen goods at -18 C with a
# -15 C limit (the Codex quick-frozen rule below), chilled paneer at +1 C with a
# +4 C limit. It was 6 C, which set paneer to -2 C - i.e. froze it.
SETPOINT_MARGIN_C = 3.0

# High humidity means frost on the evaporator coil, which costs cooling power.
# Small effect, included because the brief asks humidity to actually do work.
HUMIDITY_FROST_PENALTY = 0.10  # up to 10% of cooling power at 100% RH

# Q10: every 10 C above the safe threshold roughly doubles the spoilage rate.
# Standard food-science rule of thumb, capped so the demo cannot run away.
Q10_BASE = 2.0
MAX_SHELF_LIFE_MULTIPLIER = 6.0

# Congestion: fraction of base ETA added by each traffic band, modulated by a
# rush-hour curve on the simulated clock.
TRAFFIC_CONGESTION_FACTOR = {"LOW": 0.04, "MEDIUM": 0.12, "HIGH": 0.26, "SEVERE": 0.42}

# Road incidents clear over time. Points of delay shed per simulated hour.
INCIDENT_CLEARANCE_PER_HOUR = 6.0

# An injected weather front passes rather than sitting over the lane forever.
# Degrees of ambient offset shed per simulated hour. Recovery is therefore as
# causal as escalation: conditions improve and the risk follows, unprompted.
AMBIENT_OFFSET_DECAY_PER_HOUR = 1.5

# Sensor readings are generated every Nth tick; the maintenance features look
# at rate-of-change over 6 readings, so one per tick would make the window far
# too short to be meaningful.
SENSOR_READING_EVERY_N_TICKS = 2
MAX_READINGS_PER_MACHINE = 240
MAX_ASSESSMENTS_PER_SHIPMENT = 180

# Only persist a new RiskAssessment audit row when the number actually moved,
# so the trend chart stays readable and SQLite stays small.
ASSESSMENT_MELT_DELTA = 0.3


# ---------------------------------------------------------------------------
# Environment / clock
# ---------------------------------------------------------------------------


def environment(db: Session) -> EnvironmentState:
    """The singleton clock row, created on first use."""
    state = db.get(EnvironmentState, 1)
    if state is None:
        state = EnvironmentState(id=1, sim_minutes=0.0, tick_count=0, weather_mode="AUTO")
        db.add(state)
        db.flush()
    clock.sync(state.started_at, state.sim_minutes)
    return state


def waypoints(db: Session) -> list[weather.Waypoint]:
    """Distinct weather waypoints across every route currently in play."""
    seen: dict[str, weather.Waypoint] = {}
    for route in db.query(Route).all():
        if not route.weather_city:
            continue
        seen.setdefault(
            route.weather_city,
            weather.Waypoint(city=route.weather_city, lat=route.weather_lat, lon=route.weather_lon),
        )
    return list(seen.values())


def rush_hour_factor(sim_minutes: float) -> float:
    """1.0 off-peak, up to ~1.8 at the morning and evening peaks.

    A deterministic function of the simulated clock, so congestion breathes
    over the demo without being random.
    """
    hour = (sim_minutes / 60.0) % 24.0
    morning = math.exp(-((hour - 9.5) ** 2) / 4.0)
    evening = math.exp(-((hour - 18.5) ** 2) / 5.0)
    return 1.0 + 0.8 * max(morning, evening)


# ---------------------------------------------------------------------------
# Ambient conditions for a lane
# ---------------------------------------------------------------------------


def ambient_for_route(
    db: Session, route: Route | None, state: EnvironmentState
) -> tuple[float, float, str, str]:
    """(temperature_c, humidity_pct, weather_level, source) on this lane.

    Reads the stored observation for the lane's waypoint. `ambient_offset_c`
    and the HEAT_STORM mode are the injected-scenario knobs; when they are in
    play the source is reported as SIMULATED_INJECTED rather than LIVE, because
    the reading is no longer what Open-Meteo said.
    """
    observation = weather.latest(db, route.weather_city) if route is not None else None
    if observation is None:
        fallback = weather.simulate(
            weather.Waypoint("Unknown", 19.076, 72.877), state.sim_minutes
        )
        temperature = fallback["temperature_c"]
        humidity = fallback["humidity_pct"]
        level = fallback["weather_level"]
        source = weather.FALLBACK
    else:
        temperature = float(observation.temperature_c)
        humidity = float(observation.humidity_pct)
        level = observation.weather_level
        source = observation.source

    if state.weather_mode == "HEAT_STORM":
        temperature += float(state.ambient_offset_c)
        humidity = min(100.0, humidity + 18.0)
        # A heat-plus-storm front: re-band with the injected numbers rather than
        # simply writing "STORM" over the top of it.
        level = weather.classify(temperature, 9.0, 52.0, 95)
        source = weather.INJECTED
    elif state.ambient_offset_c:
        temperature += float(state.ambient_offset_c)
        level = weather.classify(temperature, 0.0, 0.0, 0)
        source = weather.INJECTED

    return temperature, humidity, level, source


# ---------------------------------------------------------------------------
# Machine wear -> sensors -> health
# ---------------------------------------------------------------------------


def advance_machine(
    db: Session,
    machine: Machine,
    dt_hours: float,
    ambient_c: float,
    humidity_pct: float,
    write_reading: bool,
    rng: random.Random,
) -> None:
    """Integrate one machine forward: wear, then sensors, then health.

    Cooling efficiency is the state variable and `degradation_rate_per_hour` is
    its derivative. Health is a pure function of efficiency, so the two can
    never tell contradictory stories. Sensor values are generated FROM the
    efficiency, which is why the anomaly detector reacts to real degradation
    rather than to an injected outlier.
    """
    wear = float(machine.degradation_rate_per_hour) * dt_hours
    # Working against hotter ambient wears the unit slightly faster.
    if ambient_c > 34.0:
        wear *= 1.0 + (ambient_c - 34.0) * 0.03
    efficiency = float(machine.cooling_efficiency) - wear
    machine.cooling_efficiency = round(max(EFFICIENCY_FLOOR - 12.0, min(NOMINAL_EFFICIENCY, efficiency)), 2)
    machine.operating_hours = round(float(machine.operating_hours) + dt_hours, 3)
    machine.health_score = round(
        max(1.0, min(100.0, health_for_efficiency(machine.cooling_efficiency))), 2
    )

    if not write_reading:
        return

    values = sensors_for_efficiency(machine.cooling_efficiency)
    # A little measurement noise, so the IsolationForest is not fed a
    # suspiciously perfect line.
    values["temperature"] = round(values["temperature"] + rng.uniform(-0.2, 0.2), 2)
    values["vibration"] = round(max(0.2, values["vibration"] + rng.uniform(-0.05, 0.05)), 3)
    values["current"] = round(max(1.0, values["current"] + rng.uniform(-0.08, 0.08)), 3)
    db.add(
        SensorReading(
            machine_id=machine.id,
            operating_hours=machine.operating_hours,
            humidity=round(humidity_pct, 1),
            **values,
        )
    )


def prune_readings(db: Session, machine: Machine) -> None:
    count = db.query(SensorReading).filter(SensorReading.machine_id == machine.id).count()
    if count <= MAX_READINGS_PER_MACHINE:
        return
    stale = (
        db.query(SensorReading.id)
        .filter(SensorReading.machine_id == machine.id)
        .order_by(SensorReading.id.asc())
        .limit(count - MAX_READINGS_PER_MACHINE)
        .all()
    )
    db.query(SensorReading).filter(SensorReading.id.in_([row[0] for row in stale])).delete(
        synchronize_session=False
    )


# ---------------------------------------------------------------------------
# Route delay -> ETA
# ---------------------------------------------------------------------------


def advance_route(
    db: Session, route: Route, state: EnvironmentState, dt_hours: float
) -> None:
    """Recompute this lane's delay from its three causes.

    `delay_minutes` is never assigned from outside; it is always the sum of an
    incident term that decays, a congestion term driven by the traffic band and
    the simulated hour, and a weather term from the lane's own observation.
    """
    _, _, weather_level, _ = ambient_for_route(db, route, state)
    route.weather_level = weather_level

    # Incidents clear on their own.
    route.incident_delay_minutes = round(
        max(0.0, float(route.incident_delay_minutes) - INCIDENT_CLEARANCE_PER_HOUR * dt_hours), 2
    )

    base = float(route.eta_minutes)
    congestion = TRAFFIC_CONGESTION_FACTOR.get(route.traffic_level, 0.06)
    route.congestion_delay_minutes = round(base * congestion * rush_hour_factor(state.sim_minutes), 2)
    route.weather_delay_minutes = round(base * weather.delay_factor(weather_level), 2)
    route.delay_minutes = round(
        route.incident_delay_minutes
        + route.congestion_delay_minutes
        + route.weather_delay_minutes,
        2,
    )


# ---------------------------------------------------------------------------
# Cargo thermal model -> excursion -> shelf life
# ---------------------------------------------------------------------------


def cooling_power(efficiency: float, humidity_pct: float) -> float:
    """Degrees per hour of pull-down this unit can currently deliver."""
    frost = 1.0 - HUMIDITY_FROST_PENALTY * max(0.0, humidity_pct - 60.0) / 40.0
    return MAX_COOLING_C_PER_HOUR * max(0.0, efficiency / 100.0) * max(0.6, frost)


def thermal_explanation(
    ambient_c: float, humidity_pct: float, efficiency: float, cargo_c: float, safe_max: float
) -> dict:
    """The thermal balance in numbers, for the UI to display rather than derive.

    Kept here so React never re-implements the model: the page shows what this
    returns. `equilibrium_c` is where the box settles if nothing else changes,
    which is the single most useful number for explaining why a shipment is or
    is not in trouble.
    """
    extraction = cooling_power(efficiency, humidity_pct)
    ingress = BOX_CONDUCTANCE_PER_HOUR * (ambient_c - cargo_c)
    equilibrium = ambient_c - extraction / BOX_CONDUCTANCE_PER_HOUR
    return {
        "ambient_c": round(ambient_c, 1),
        "cargo_c": round(cargo_c, 1),
        "safe_max_c": round(safe_max, 1),
        "cooling_power_c_per_hour": round(extraction, 2),
        "heat_ingress_c_per_hour": round(ingress, 2),
        "net_c_per_hour": round(ingress - extraction, 2),
        "equilibrium_c": round(equilibrium, 1),
        "will_breach": equilibrium > safe_max,
        "explanation": (
            f"Heat leaks in at {ingress:.1f} C/h against {extraction:.1f} C/h of cooling, "
            f"so the box is heading for {equilibrium:.0f} C. "
            + (
                f"That is above the {safe_max:.0f} C safe maximum, so the cold chain fails."
                if equilibrium > safe_max
                else f"That is below the {safe_max:.0f} C safe maximum, so the cold chain holds."
            )
        ),
    }


def advance_shipment(
    db: Session,
    shipment: Shipment,
    product: Product,
    dt_hours: float,
    ambient_c: float,
    humidity_pct: float,
    reefer_efficiency: float,
) -> None:
    """Integrate cargo temperature, excursion minutes, shelf life and progress.

    This is the function that earns the excursion figure. Heat leaks in
    proportional to the ambient/cargo gap; the reefer pulls it back out in
    proportion to its efficiency. Whichever wins decides whether the cold chain
    holds, and the excursion counter only advances while the cargo is genuinely
    above the product's safe temperature.
    """
    safe_max = float(product.safe_transit_temp_c)
    setpoint = safe_max - SETPOINT_MARGIN_C
    cargo = float(shipment.cargo_temperature_c)

    ingress = BOX_CONDUCTANCE_PER_HOUR * (ambient_c - cargo)
    extraction = cooling_power(reefer_efficiency, humidity_pct)
    # The unit cannot chill below its setpoint, so extraction tapers off as the
    # box approaches it - otherwise a healthy reefer would drive to absolute
    # zero over a long enough leg.
    if cargo <= setpoint:
        extraction *= max(0.0, min(1.0, (cargo - (setpoint - 2.0)) / 2.0))

    cargo_next = cargo + (ingress - extraction) * dt_hours
    shipment.cargo_temperature_c = round(max(-30.0, min(ambient_c, cargo_next)), 2)
    shipment.ambient_temperature_c = round(ambient_c, 2)

    # Excursion accrues ONLY while genuinely out of range.
    if shipment.cargo_temperature_c > safe_max:
        shipment.minutes_outside_safe_range = round(
            float(shipment.minutes_outside_safe_range) + dt_hours * 60.0, 2
        )

    # Q10: shelf life burns faster above the safe threshold.
    excess_c = max(0.0, shipment.cargo_temperature_c - safe_max)
    multiplier = min(MAX_SHELF_LIFE_MULTIPLIER, Q10_BASE ** (excess_c / 10.0))
    shipment.remaining_shelf_life_hours = round(
        max(0.0, float(shipment.remaining_shelf_life_hours) - dt_hours * multiplier), 3
    )

    route = risk_engine.selected_route(shipment)
    if route is not None:
        total_minutes = float(route.eta_minutes) + float(route.delay_minutes)
        if total_minutes > 0:
            shipment.progress_fraction = round(
                min(1.0, float(shipment.progress_fraction) + (dt_hours * 60.0) / total_minutes), 4
            )


def effective_efficiency(shipment: Shipment, route: Route | None) -> float:
    """Cooling efficiency actually acting on this cargo right now.

    Mirrors `risk_engine.reefer_health_for`: a lane that transfers the load to a
    standby unit carries that unit's efficiency instead.
    """
    if route is not None and route.reefer_health_override is not None:
        return float(NOMINAL_EFFICIENCY) - (100.0 - float(route.reefer_health_override)) * (
            18.0 / 51.0
        )
    if shipment.machine is not None:
        return float(shipment.machine.cooling_efficiency)
    return NOMINAL_EFFICIENCY


# ---------------------------------------------------------------------------
# Inventory drawdown
# ---------------------------------------------------------------------------


def advance_inventory(db: Session, dt_hours: float) -> None:
    """Consume stock at the product's daily rate so stockout risk moves."""
    for row in db.query(Inventory).all():
        product = row.product
        if product is None or not product.daily_demand_rate:
            continue
        row.current_stock = round(
            max(0.0, float(row.current_stock) - float(product.daily_demand_rate) * dt_hours / 24.0),
            2,
        )


def prune_assessments(db: Session, shipment: Shipment) -> None:
    count = db.query(RiskAssessment).filter(RiskAssessment.shipment_id == shipment.id).count()
    if count <= MAX_ASSESSMENTS_PER_SHIPMENT:
        return
    stale = (
        db.query(RiskAssessment.id)
        .filter(RiskAssessment.shipment_id == shipment.id)
        .order_by(RiskAssessment.id.asc())
        .limit(count - MAX_ASSESSMENTS_PER_SHIPMENT)
        .all()
    )
    db.query(RiskAssessment).filter(RiskAssessment.id.in_([row[0] for row in stale])).delete(
        synchronize_session=False
    )


# ---------------------------------------------------------------------------
# The tick
# ---------------------------------------------------------------------------


def tick(
    db: Session,
    sim_minutes: float | None = None,
    rng: random.Random | None = None,
    evaluate_decisions: bool = True,
) -> dict:
    """Advance the whole world by one step and re-derive every prediction.

    Ordering matters and is deliberate:
      1. clock          - so every downstream term integrates the same dt
      2. routes         - delay/ETA before anything reads them
      3. machines       - wear and sensors before health is used as a cooling term
      4. maintenance    - anomaly + failure probability from the new readings
      5. shipments      - thermal integration using the new machine state
      6. risk + decision - derive Melt Index, spoilage, loss, recommendation
    """
    from app.services import decision_engine, maintenance

    rng = rng or random.Random()
    state = environment(db)
    step = float(sim_minutes if sim_minutes is not None else settings.sim_minutes_per_tick)
    dt_hours = step / 60.0

    state.sim_minutes = round(float(state.sim_minutes) + step, 3)
    state.tick_count = int(state.tick_count) + 1
    # Everything written during this tick is stamped with the moment it reached.
    clock.sync(state.started_at, state.sim_minutes)

    # Let any injected weather front move on.
    if state.ambient_offset_c > 0:
        state.ambient_offset_c = round(
            max(0.0, float(state.ambient_offset_c) - AMBIENT_OFFSET_DECAY_PER_HOUR * dt_hours), 3
        )
        if state.ambient_offset_c == 0.0:
            state.weather_mode = "AUTO"
    write_reading = state.tick_count % SENSOR_READING_EVERY_N_TICKS == 0

    # 2. Routes first: delay feeds ETA risk and progress.
    for route in db.query(Route).all():
        advance_route(db, route, state, dt_hours)
    db.flush()

    # 3 + 4. Machines: wear, sensors, then the maintenance assessment.
    machines = db.query(Machine).all()
    for machine in machines:
        carrying = machine.active_shipments
        shipment = carrying[0] if carrying else None
        route = risk_engine.selected_route(shipment) if shipment is not None else None
        ambient_c, humidity_pct, _, _ = ambient_for_route(db, route, state)
        advance_machine(db, machine, dt_hours, ambient_c, humidity_pct, write_reading, rng)
    db.flush()
    for machine in machines:
        if write_reading:
            prune_readings(db, machine)
        db.refresh(machine)
        maintenance.refresh(db, machine)

    # 5. Shipments: thermal integration on the new machine state.
    shipments = db.query(Shipment).filter(Shipment.status != DELIVERED).all()
    for shipment in shipments:
        product = shipment.product
        if product is None:
            continue
        route = risk_engine.selected_route(shipment)
        ambient_c, humidity_pct, _, _ = ambient_for_route(db, route, state)
        advance_shipment(
            db,
            shipment,
            product,
            dt_hours,
            ambient_c,
            humidity_pct,
            effective_efficiency(shipment, route),
        )

    advance_inventory(db, dt_hours)
    db.flush()

    # 5b. Loads that reached their destination are delivered, and their lanes
    #     get the next load. New loads are routed and scored in THIS tick, so
    #     they never appear on the board unscored.
    from app.simulation import dispatch

    new_loads = dispatch.deliver_arrivals(db)
    for load in new_loads:
        for route in load.routes:
            advance_route(db, route, state, dt_hours=0.0)
    shipments = [s for s in shipments if s.status != DELIVERED] + new_loads

    # 6. Derive every prediction from the state we just produced.
    workflows = []
    for shipment in shipments:
        previous = float(shipment.melt_index)
        assessment = risk_engine.recalculate(db, shipment)
        if abs(assessment.melt_index - previous) < ASSESSMENT_MELT_DELTA:
            # Nothing moved enough to be worth an audit row.
            db.delete(assessment)
        else:
            prune_assessments(db, shipment)
        if evaluate_decisions:
            workflow = decision_engine.evaluate_shipment(db, shipment)
            if workflow is not None:
                workflows.append(workflow)

    if evaluate_decisions:
        for machine in machines:
            assessment = maintenance.assess(machine)
            workflow = decision_engine.evaluate_machine(db, machine, assessment)
            if workflow is not None:
                workflows.append(workflow)

    alerts.prune(db)
    db.commit()
    return {
        "tick": state.tick_count,
        "sim_minutes": state.sim_minutes,
        "shipments_advanced": len(shipments),
        "machines_advanced": len(machines),
        "workflows_touched": len(workflows),
    }


def settle(db: Session, minutes: float, rng: random.Random | None = None) -> dict:
    """Run enough ticks to advance `minutes` of simulated time, synchronously.

    Used by the scenario triggers. An event changes a ROOT CAUSE and then the
    world is integrated forward, so the HTTP response already carries the
    consequence. This is what makes the trigger causal rather than a delta: the
    caller never states what the Melt Index should become.
    """
    step = float(settings.settle_step_minutes)
    ticks = max(1, int(round(minutes / step)))
    result: dict = {}
    for _ in range(ticks):
        result = tick(db, sim_minutes=step, rng=rng)
    result["settled_minutes"] = ticks * step
    return result
