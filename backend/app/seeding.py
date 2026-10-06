"""Builds the baseline database state from `seed_config` (§29).

`POST /api/simulation/reset` calls `reseed()`, which is what lets the whole
scripted demo be re-run without restarting the server (§25).

All data produced here is synthetic and seeded, so a rebuild is byte-identical
every time — the property the §39 "runs three times with identical results"
checklist item depends on.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.ml.synthetic import demand_series, efficiency_for_health, sensor_history
from app.models import (
    Alert,
    EnvironmentState,
    DemandHistory,
    Forecast,
    Inventory,
    Machine,
    Product,
    RiskAssessment,
    Route,
    SensorReading,
    Shipment,
    SimulationEvent,
    WeatherObservation,
    Workflow,
)
from app.seed_config import (
    BASELINE_DEGRADATION_RATE,
    CITIES,
    MACHINES,
    PRODUCTS,
    SHIPMENTS,
    WAYPOINTS,
)
from app.services import decision_engine, forecasting, maintenance, risk_engine, weather
from app.simulation import clock, physics
from app.services.alerts import raise_alert

DEMAND_HISTORY_DAYS = 90
READINGS_PER_MACHINE = 50
READING_INTERVAL_HOURS = 4.0

# Deletion order respects foreign keys (children first).
#
# WeatherObservation is deliberately ABSENT. Weather is an external fact rather
# than part of the demo's baseline, so a reset must not discard readings that
# Open-Meteo really returned - otherwise pressing Reset silently downgrades the
# feed from LIVE to SIMULATED until the next scheduled refresh, up to ten
# minutes later.
_DELETE_ORDER = (
    SimulationEvent,
    EnvironmentState,
    Workflow,
    RiskAssessment,
    Alert,
    Route,
    Shipment,
    SensorReading,
    Machine,
    Forecast,
    DemandHistory,
    Inventory,
    Product,
)


def clear(db: Session) -> None:
    for model in _DELETE_ORDER:
        db.query(model).delete(synchronize_session=False)
    db.flush()
    # Drop the now-deleted rows from the identity map. Without this, a reset on
    # a long-lived session (the /simulation/reset path) rebuilds objects whose
    # primary keys collide with stale identities.
    db.expunge_all()


def _stable_seed(code: str) -> int:
    """Deterministic per-machine RNG seed — `hash()` is salted per process, so
    it would break reproducibility across restarts."""
    return sum((i + 1) * ord(ch) for i, ch in enumerate(code)) % 100_000


EPISODE_START_MINUTES = 6 * 60.0  # the twin opens at 06:00, off-peak


def add_shipment(
    db: Session,
    spec: dict,
    product: Product,
    machine: Machine | None,
    code: str | None = None,
    is_hero: bool | None = None,
    fresh: bool = False,
) -> Shipment:
    """Create one load and its candidate routes from a SHIPMENTS spec.

    Shared by the seed and by `simulation/dispatch.py`, which puts a new load on
    a lane when the last one is delivered. `fresh=True` is that case: the load
    leaves the dock in spec, with the lane's standard shelf life and no
    excursion on the clock.
    """
    origin = CITIES[spec["origin_city"]]
    destination = CITIES[spec["destination_city"]]
    shipment = Shipment(
        code=code or spec["code"],
        product_id=product.id,
        origin_city=spec["origin_city"],
        destination_city=spec["destination_city"],
        shipment_value_inr=spec["shipment_value_inr"],
        machine_id=machine.id if machine is not None else None,
        remaining_shelf_life_hours=spec["remaining_shelf_life_hours"],
        minutes_outside_safe_range=0.0 if fresh else spec["minutes_outside_safe_range"],
        origin_lat=origin[0],
        origin_lon=origin[1],
        dest_lat=destination[0],
        dest_lon=destination[1],
        is_hero=spec.get("is_hero", False) if is_hero is None else is_hero,
        # Dispatched at the setpoint the reefer is holding, so the thermal
        # model starts from a physically consistent state rather than from
        # a number chosen to make the demo work.
        cargo_temperature_c=round(product.safe_transit_temp_c - physics.SETPOINT_MARGIN_C, 2),
    )
    db.add(shipment)
    db.flush()
    for route_spec in spec["routes"]:
        waypoint_name = route_spec["waypoint"]
        waypoint_lat, waypoint_lon = WAYPOINTS[waypoint_name]
        db.add(
            Route(
                shipment_id=shipment.id,
                label=route_spec["label"],
                eta_minutes=route_spec["eta_minutes"],
                # A placeholder: the first physics pass replaces it with
                # incident + congestion + weather.
                delay_minutes=route_spec.get("delay_minutes", 0.0),
                weather_city=waypoint_name,
                weather_lat=waypoint_lat,
                weather_lon=waypoint_lon,
                traffic_level=route_spec.get("traffic_level", "LOW"),
                weather_level=route_spec.get("weather_level", "CLEAR"),
                is_current=route_spec.get("is_current", False),
                is_selected=route_spec.get("is_selected", False),
                reefer_health_override=route_spec.get("reefer_health_override"),
                notes=route_spec.get("notes", ""),
            )
        )
    db.flush()
    db.refresh(shipment)
    return shipment


def build(db: Session) -> None:
    # Point twin time at the new episode FIRST, so every row written while
    # seeding - histories, workflows, alerts - is stamped in the same clock the
    # simulation will then advance.
    real_now = clock.wall_now()
    clock.sync(real_now, EPISODE_START_MINUTES)
    now = clock.now()

    # --- products, inventory, demand history ------------------------------
    products: dict[str, Product] = {}
    for spec in PRODUCTS:
        product = Product(
            name=spec["name"],
            category=spec["category"],
            unit_shelf_life_hours=spec["unit_shelf_life_hours"],
            unit_value_inr=spec["unit_value_inr"],
            safe_transit_temp_c=spec["safe_transit_temp_c"],
            daily_demand_rate=spec["daily_demand_rate"],
        )
        db.add(product)
        db.flush()
        products[product.name] = product

        db.add(
            Inventory(
                product_id=product.id,
                current_stock=spec["current_stock"],
                warehouse_city=spec["warehouse_city"],
            )
        )
        series = demand_series(
            base=spec["base"],
            weekly_amplitude=spec["weekly_amplitude"],
            trend_per_day=spec["trend_per_day"],
            noise_sd=spec["noise_sd"],
            days=DEMAND_HISTORY_DAYS,
            seed=_stable_seed(spec["name"]),
        )
        first_day = now - timedelta(days=DEMAND_HISTORY_DAYS)
        for row in series:
            db.add(
                DemandHistory(
                    product_id=product.id,
                    day=first_day + timedelta(days=row["day_index"]),
                    units=row["units"],
                    is_festival=row["is_festival"],
                )
            )
    db.flush()

    # --- machines and their sensor history --------------------------------
    machines: dict[str, Machine] = {}
    for spec in MACHINES:
        efficiency = efficiency_for_health(spec["health_score"])
        machine = Machine(
            code=spec["code"],
            type=spec["type"],
            location=spec["location"],
            health_score=spec["health_score"],
            cooling_efficiency=round(efficiency, 2),
            baseline_cooling_efficiency=round(efficiency, 2),
            is_hero=spec.get("is_hero", False),
            degradation_rate_per_hour=spec.get(
                "degradation_rate_per_hour", BASELINE_DEGRADATION_RATE
            ),
            operating_hours=round(READING_INTERVAL_HOURS * (READINGS_PER_MACHINE - 1), 2),
        )
        db.add(machine)
        db.flush()
        machines[machine.code] = machine

        history = sensor_history(
            end_health=spec["health_score"],
            count=READINGS_PER_MACHINE,
            hours_step=READING_INTERVAL_HOURS,
            seed=_stable_seed(spec["code"]),
        )
        first_ts = now - timedelta(hours=READING_INTERVAL_HOURS * (READINGS_PER_MACHINE - 1))
        for i, values in enumerate(history):
            db.add(
                SensorReading(
                    machine_id=machine.id,
                    timestamp=first_ts + timedelta(hours=READING_INTERVAL_HOURS * i),
                    **values,
                )
            )
    db.flush()

    # Derive anomaly score / failure probability / RUL / status from readings.
    for machine in machines.values():
        db.refresh(machine)
        maintenance.refresh(db, machine)

    # --- shipments and routes ---------------------------------------------
    hero_shipments: list[Shipment] = []
    other_shipments: list[Shipment] = []
    for spec in SHIPMENTS:
        shipment = add_shipment(
            db,
            spec,
            product=products[spec["product"]],
            machine=machines[spec["machine"]] if spec.get("machine") else None,
        )
        (hero_shipments if shipment.is_hero else other_shipments).append(shipment)

    # --- environment, weather and DERIVED route delays --------------------
    # The clock starts at 06:00 so the demo opens off-peak and walks into the
    # morning traffic peak on its own.
    db.add(
        EnvironmentState(
            id=1,
            sim_minutes=EPISODE_START_MINUTES,
            tick_count=0,
            weather_mode="AUTO",
            started_at=real_now,
        )
    )
    db.flush()
    state = physics.environment(db)

    # Give every waypoint an ambient to work against from the very first tick,
    # but only where we do not already have one: a real Open-Meteo reading
    # already on file is better than a simulated one and survives the reset.
    # This path is deliberately offline, so a reset is instant and tests never
    # touch the network.
    for waypoint in physics.waypoints(db):
        if weather.latest(db, waypoint.city) is not None:
            continue
        db.add(
            WeatherObservation(
                city=waypoint.city,
                lat=waypoint.lat,
                lon=waypoint.lon,
                **weather.simulate(waypoint, state.sim_minutes),
            )
        )
    db.flush()

    # Derive every lane's delay from the formula rather than trusting the seed.
    for route in db.query(Route).all():
        physics.advance_route(db, route, state, dt_hours=0.0)
    db.flush()

    # --- baseline risk ----------------------------------------------------
    for shipment in hero_shipments + other_shipments:
        risk_engine.recalculate(db, shipment)

    # Non-hero shipments get their decision pass at seed time so the dashboard
    # and Workflows page have realistic content before the presenter starts.
    #
    # The HERO shipment deliberately does NOT: at baseline its optimizer would
    # find a small, high-confidence improvement and auto-execute it under the
    # §21 rules, silently rerouting SC-1042 before the demo begins. Its first
    # decision pass happens on the first simulation trigger.
    for shipment in other_shipments:
        decision_engine.evaluate_shipment(db, shipment, allow_auto_execute=False)

    forecasting.refresh_forecasts(db)

    raise_alert(
        db,
        "INFO",
        "Twin reset to its 06:00 baseline. All loads dispatched and in transit.",
        dedupe=False,
    )
    db.commit()


def reseed(db: Session) -> None:
    clear(db)
    build(db)


def seed_if_empty(db: Session) -> bool:
    """Returns True if it actually seeded."""
    if db.query(Product).count() > 0:
        return False
    build(db)
    return True
