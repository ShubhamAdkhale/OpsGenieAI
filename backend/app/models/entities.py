"""SQLAlchemy models — implements the schema in §13.

A few columns are additions beyond the §13 table list; each is marked with
"# extra:" and a reason. They exist because §18/§25 need somewhere to store
state that §13 only implied.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.simulation import clock


# A shipment's terminal status: it reached its destination. It is kept as a
# record but drops out of everything that describes the network right now.
DELIVERED = "DELIVERED"


def utcnow() -> datetime:
    """Real wall-clock time. Only for things that happen in the real world."""
    return datetime.now(timezone.utc)


def twin_now() -> datetime:
    """Twin time (simulation/clock.py): the default for every simulated record."""
    return clock.now()


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    category: Mapped[str] = mapped_column(String(40))
    # The in-transit safe window, not the retail shelf life — this is the
    # denominator of ShelfLifeRisk in §18.
    unit_shelf_life_hours: Mapped[float] = mapped_column(Float)
    unit_value_inr: Mapped[float] = mapped_column(Float)
    # extra: the temperature above which this product is out of its cold chain.
    # The physics tick compares live cargo temperature against THIS to decide
    # whether excursion minutes accumulate, so it is the causal threshold
    # behind TemperatureRisk rather than a hardcoded delta.
    safe_transit_temp_c: Mapped[float] = mapped_column(Float, default=-15.0)
    # extra: units consumed per day, used by the physics tick to draw down
    # inventory so stockout probability moves on its own.
    daily_demand_rate: Mapped[float] = mapped_column(Float, default=0.0)

    inventory = relationship("Inventory", back_populates="product", cascade="all, delete-orphan")
    forecasts = relationship("Forecast", back_populates="product", cascade="all, delete-orphan")
    shipments = relationship("Shipment", back_populates="product")


class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    current_stock: Mapped[float] = mapped_column(Float)
    warehouse_city: Mapped[str] = mapped_column(String(60))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=twin_now)

    product = relationship("Product", back_populates="inventory")


class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    type: Mapped[str] = mapped_column(String(40))  # refrigeration_unit|conveyor_motor|compressor
    location: Mapped[str] = mapped_column(String(80))
    health_score: Mapped[float] = mapped_column(Float, default=100.0)
    failure_probability: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_failure_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="HEALTHY")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=twin_now, onupdate=twin_now)

    # extra: current cooling efficiency %, the input to the RUL heuristic (§17).
    cooling_efficiency: Mapped[float] = mapped_column(Float, default=95.0)
    # extra: efficiency at dispatch. §24 reports the drop against THIS, not
    # against nominal, so "efficiency dropped 18%" means what a manager expects.
    baseline_cooling_efficiency: Mapped[float] = mapped_column(Float, default=95.0)
    # extra: latest IsolationForest score, surfaced on the maintenance page.
    anomaly_score: Mapped[float] = mapped_column(Float, default=0.0)
    anomaly_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    # extra: hero assets are seeded deliberately; the physics tick still
    # advances them, because a control tower with a frozen sensor feed is a
    # slide deck, not a control tower.
    is_hero: Mapped[bool] = mapped_column(Boolean, default=False)
    # extra: cooling-efficiency points lost per operating hour. THE causal knob
    # for predictive maintenance — the degradation event raises this rate, and
    # everything downstream (sensors, anomaly, health, cargo temperature,
    # spoilage risk) follows from integrating it over time.
    degradation_rate_per_hour: Mapped[float] = mapped_column(Float, default=0.02)
    # extra: cumulative runtime, carried on the row so the physics tick and the
    # maintenance features agree on one clock.
    operating_hours: Mapped[float] = mapped_column(Float, default=0.0)

    readings = relationship(
        "SensorReading",
        back_populates="machine",
        cascade="all, delete-orphan",
        order_by="SensorReading.timestamp",
    )
    shipments = relationship("Shipment", back_populates="machine")

    @property
    def active_shipments(self) -> list["Shipment"]:
        """The loads this unit is carrying now - delivered ones are history."""
        return [s for s in self.shipments if s.status != DELIVERED]


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=twin_now)
    temperature: Mapped[float] = mapped_column(Float)
    vibration: Mapped[float] = mapped_column(Float)
    current: Mapped[float] = mapped_column(Float)
    pressure: Mapped[float] = mapped_column(Float)
    cooling_efficiency: Mapped[float] = mapped_column(Float)
    operating_hours: Mapped[float] = mapped_column(Float)
    # extra: bay humidity. Reported on the machine page and used by the frost
    # term in the physics tick; deliberately NOT a maintenance model feature,
    # so the trained models keep their original feature vector.
    humidity: Mapped[float] = mapped_column(Float, default=55.0)

    machine = relationship("Machine", back_populates="readings")


Index("ix_sensor_machine_time", SensorReading.machine_id, SensorReading.timestamp)


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    origin_city: Mapped[str] = mapped_column(String(60))
    destination_city: Mapped[str] = mapped_column(String(60))
    shipment_value_inr: Mapped[float] = mapped_column(Float)
    machine_id: Mapped[int | None] = mapped_column(ForeignKey("machines.id"), nullable=True)
    remaining_shelf_life_hours: Mapped[float] = mapped_column(Float)
    melt_index: Mapped[float] = mapped_column(Float, default=0.0)
    spoilage_probability: Mapped[float] = mapped_column(Float, default=0.0)
    expected_loss_inr: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(24), default="SAFE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=twin_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=twin_now, onupdate=twin_now)

    # extra: cumulative cold-chain excursion, the TemperatureRisk input (§18).
    minutes_outside_safe_range: Mapped[float] = mapped_column(Float, default=0.0)
    # extra: recorded when a reroute is approved, shown as "loss avoided" (§7 step 9).
    loss_avoided_inr: Mapped[float] = mapped_column(Float, default=0.0)
    # extra: map pins for MapView (§28).
    origin_lat: Mapped[float] = mapped_column(Float, default=19.0760)
    origin_lon: Mapped[float] = mapped_column(Float, default=72.8777)
    dest_lat: Mapped[float] = mapped_column(Float, default=18.5204)
    dest_lon: Mapped[float] = mapped_column(Float, default=73.8567)
    # extra: hero shipment is the one the demo script drives.
    is_hero: Mapped[bool] = mapped_column(Boolean, default=False)
    # extra: LIVE simulated cargo temperature, integrated by the physics tick
    # from ambient weather, reefer cooling power and box conductance. This is
    # the variable that earns the excursion minutes — nothing assigns them.
    cargo_temperature_c: Mapped[float] = mapped_column(Float, default=-18.0)
    # extra: fraction of the current route completed, advanced by the tick.
    progress_fraction: Mapped[float] = mapped_column(Float, default=0.0)
    # extra: ambient temperature last seen on this shipment's lane, kept so the
    # explanation can name the number that drove the heat ingress.
    ambient_temperature_c: Mapped[float] = mapped_column(Float, default=30.0)

    product = relationship("Product", back_populates="shipments")
    machine = relationship("Machine", back_populates="shipments")

    @property
    def in_transit(self) -> bool:
        return self.status != DELIVERED

    routes = relationship(
        "Route", back_populates="shipment", cascade="all, delete-orphan", order_by="Route.id"
    )
    assessments = relationship(
        "RiskAssessment",
        back_populates="shipment",
        cascade="all, delete-orphan",
        order_by="RiskAssessment.id",
    )


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    label: Mapped[str] = mapped_column(String(120))
    eta_minutes: Mapped[float] = mapped_column(Float)
    traffic_level: Mapped[str] = mapped_column(String(16), default="LOW")
    weather_level: Mapped[str] = mapped_column(String(16), default="CLEAR")
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)

    # extra: TOTAL delay on this lane. DERIVED every physics tick as
    # incident + congestion + weather, so nothing sets a delay directly.
    delay_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    # extra: the three causes that sum into delay_minutes, kept separately so
    # the UI can attribute the ETA slip instead of just showing a total.
    incident_delay_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    congestion_delay_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    weather_delay_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    # extra: the waypoint whose weather governs this lane. Two routes out of the
    # same city can sit under different weather, which is what lets the
    # optimizer prefer a longer lane in better conditions.
    weather_city: Mapped[str] = mapped_column(String(60), default="")
    weather_lat: Mapped[float] = mapped_column(Float, default=19.0760)
    weather_lon: Mapped[float] = mapped_column(Float, default=72.8777)
    # extra: an alternative route may route via a cold hub and swap the goods to
    # a healthy reefer. When set, this health is used for RefrigerationRisk
    # instead of the shipment's currently attached unit.
    reefer_health_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(String(200), default="")

    shipment = relationship("Shipment", back_populates="routes")


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    period_label: Mapped[str] = mapped_column(String(40))
    historical_demand: Mapped[float] = mapped_column(Float)
    predicted_demand: Mapped[float] = mapped_column(Float)
    projected_inventory: Mapped[float] = mapped_column(Float)
    stockout_probability: Mapped[float] = mapped_column(Float)
    recommended_reorder_qty: Mapped[float] = mapped_column(Float)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=twin_now)

    # extra: flags the §16 "<14 days of history" moving-average fallback.
    model_source: Mapped[str] = mapped_column(String(40), default="gradient_boosting")

    product = relationship("Product", back_populates="forecasts")


class DemandHistory(Base):
    """90 days of synthetic daily demand per product (§29) — training input."""

    __tablename__ = "demand_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    day: Mapped[datetime] = mapped_column(DateTime)
    units: Mapped[float] = mapped_column(Float)
    is_festival: Mapped[bool] = mapped_column(Boolean, default=False)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    related_type: Mapped[str] = mapped_column(String(20))  # shipment|machine|system
    related_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    severity: Mapped[str] = mapped_column(String(16))  # INFO|WARNING|CRITICAL
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=twin_now)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)

    # extra: identifies the STATE this alert is about, e.g.
    # "shipment-risk:SC-1042:CRITICAL". Deduplication matches on this rather
    # than on the message text, because the message embeds live numbers that
    # change every tick - so text matching produced a fresh alert every few
    # seconds and drowned the feed. A new alert now appears when the state
    # changes; while the state holds, the existing alert's message is refreshed
    # in place so the figures stay current.
    dedupe_key: Mapped[str] = mapped_column(String(120), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=twin_now, onupdate=twin_now)


class RiskAssessment(Base):
    """One row per recalculation — the audit trail that powers §24."""

    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    temperature_risk: Mapped[float] = mapped_column(Float)
    refrigeration_risk: Mapped[float] = mapped_column(Float)
    traffic_risk: Mapped[float] = mapped_column(Float)
    weather_risk: Mapped[float] = mapped_column(Float)
    shelf_life_risk: Mapped[float] = mapped_column(Float)
    eta_risk: Mapped[float] = mapped_column(Float)
    melt_index: Mapped[float] = mapped_column(Float)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=twin_now)

    # extra: the raw numbers §24 substitutes into its sentences, so the
    # explanation can be regenerated from the stored row alone.
    minutes_outside_safe_range: Mapped[float] = mapped_column(Float, default=0.0)
    cooling_efficiency_drop: Mapped[float] = mapped_column(Float, default=0.0)
    traffic_delay_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    remaining_shelf_life_hours: Mapped[float] = mapped_column(Float, default=0.0)
    weather_level: Mapped[str] = mapped_column(String(16), default="CLEAR")
    machine_code: Mapped[str] = mapped_column(String(20), default="")
    eta_margin_hours: Mapped[float] = mapped_column(Float, default=0.0)
    route_label: Mapped[str] = mapped_column(String(120), default="")

    shipment = relationship("Shipment", back_populates="assessments")


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow_type: Mapped[str] = mapped_column(String(32))
    trigger_reason: Mapped[str] = mapped_column(Text)
    related_shipment_id: Mapped[int | None] = mapped_column(
        ForeignKey("shipments.id"), nullable=True
    )
    related_machine_id: Mapped[int | None] = mapped_column(
        ForeignKey("machines.id"), nullable=True
    )
    confidence: Mapped[str] = mapped_column(String(16))  # HIGH|MEDIUM|LOW
    impact_inr: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(24))
    recommendation_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=twin_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # extra: the route a REROUTE workflow would switch to, so approving it
    # knows what to execute. Also records an OVERRIDDEN manager choice (§23).
    proposed_route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    executed_route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    resolution_note: Mapped[str] = mapped_column(Text, default="")

    def requires_approval_now(self) -> bool:
        """§23: only a PENDING_APPROVAL workflow can be approved or rejected.
        Once resolved, the record is immutable."""
        return self.status == "PENDING_APPROVAL"


class SimulationEvent(Base):
    __tablename__ = "simulation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(48))
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[int] = mapped_column(Integer)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=twin_now)


class WeatherObservation(Base):
    """One weather reading per waypoint, with its PROVENANCE recorded.

    `source` is the whole point of this table. Open-Meteo is a real, keyless
    public API and when it answers, these rows are genuinely live. When it
    times out or errors, the fallback writes a simulated row and says so, and
    the UI badges it differently. Nothing in this build ever presents a
    simulated reading as a live one.
    """

    __tablename__ = "weather_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city: Mapped[str] = mapped_column(String(60))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    temperature_c: Mapped[float] = mapped_column(Float)
    humidity_pct: Mapped[float] = mapped_column(Float)
    precipitation_mm: Mapped[float] = mapped_column(Float, default=0.0)
    wind_kph: Mapped[float] = mapped_column(Float, default=0.0)
    # CLEAR | RAIN | STORM | EXTREME — the band risk_engine.WEATHER_RISK reads.
    weather_level: Mapped[str] = mapped_column(String(16), default="CLEAR")
    condition: Mapped[str] = mapped_column(String(60), default="")
    # LIVE_OPEN_METEO | SIMULATED_FALLBACK | SIMULATED_INJECTED
    source: Mapped[str] = mapped_column(String(32), default="SIMULATED_FALLBACK")
    # Real observation time: live weather is a real-world reading, not twin time.
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def is_live(self) -> bool:
        return self.source == "LIVE_OPEN_METEO"


Index("ix_weather_city_time", WeatherObservation.city, WeatherObservation.observed_at)


class EnvironmentState(Base):
    """Singleton row: the simulation clock and the global weather mode.

    The clock is what makes the physics reproducible. A tick advances
    `sim_minutes` by a fixed step rather than reading the wall clock, so the
    same number of ticks always produces the same integration — the demo stays
    repeatable even though nothing in it is scripted.
    """

    __tablename__ = "environment_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    sim_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    tick_count: Mapped[int] = mapped_column(Integer, default=0)
    # AUTO follows the weather service. HEAT_STORM is the injected scenario.
    weather_mode: Mapped[str] = mapped_column(String(24), default="AUTO")
    # Degrees added to every ambient reading while a heat scenario is injected.
    ambient_offset_c: Mapped[float] = mapped_column(Float, default=0.0)
    # Real time the episode was reset. Twin time's epoch is midnight IST that day.
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=twin_now, onupdate=twin_now)
