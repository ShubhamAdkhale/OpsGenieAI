"""Feature builders shared by the training scripts and the runtime registry.

Keeping them in one place is the whole point: if training and inference build
features differently, the model silently gets garbage at demo time.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

SENSOR_FIELDS = ("temperature", "vibration", "current", "pressure", "cooling_efficiency")

MAINTENANCE_FEATURE_NAMES = [
    *SENSOR_FIELDS,
    "operating_hours",
    *[f"{f}_rate" for f in SENSOR_FIELDS],
]

SPOILAGE_FEATURE_NAMES = [
    "temperature_risk",
    "refrigeration_risk",
    "traffic_risk",
    "weather_risk",
    "shelf_life_risk",
    "eta_risk",
    "shipment_value_lakh",
    "unit_shelf_life_hours",
]

FORECAST_FEATURE_NAMES = [
    "day_of_week",
    "day_of_month",
    "rolling_7",
    "rolling_30",
    "trend_slope",
    "is_festival",
]

MAINTENANCE_WINDOW = 6  # §17: rate of change over the last 6 readings


def reading(**kwargs) -> SimpleNamespace:
    """A duck-typed stand-in for a SensorReading row, used by the trainers."""
    return SimpleNamespace(**kwargs)


def maintenance_features(readings: list) -> list[float]:
    """Latest raw values plus per-sensor rate of change over the window (§17)."""
    window = list(readings)[-MAINTENANCE_WINDOW:]
    if not window:
        return [0.0] * len(MAINTENANCE_FEATURE_NAMES)
    latest, first = window[-1], window[0]
    hours = max(float(latest.operating_hours) - float(first.operating_hours), 1e-6)
    raw = [float(getattr(latest, f)) for f in SENSOR_FIELDS]
    raw.append(float(latest.operating_hours))
    rates = [
        (float(getattr(latest, f)) - float(getattr(first, f))) / hours for f in SENSOR_FIELDS
    ]
    return raw + rates


RATE_FEATURE_INDICES = [MAINTENANCE_FEATURE_NAMES.index(f"{f}_rate") for f in SENSOR_FIELDS]


def rate_columns(X):
    """The rate-of-change columns of a maintenance feature matrix.

    The anomaly detector looks at these alone: an anomaly is a unit BEHAVING
    unusually - drifting, jumping - not a unit that is merely worn. Level is
    what the condition score measures. Module-level (not a lambda) so a saved
    pipeline that uses it can be unpickled.
    """
    return np.asarray(X, dtype=float)[:, RATE_FEATURE_INDICES]


def spoilage_features(components, shipment_value_inr: float, unit_shelf_life_hours: float) -> list[float]:
    """The six §18 components plus raw value and shelf life (§19)."""
    return [
        float(components.temperature_risk),
        float(components.refrigeration_risk),
        float(components.traffic_risk),
        float(components.weather_risk),
        float(components.shelf_life_risk),
        float(components.eta_risk),
        float(shipment_value_inr) / 100_000.0,
        float(unit_shelf_life_hours),
    ]


def forecast_features(
    day_of_week: int,
    day_of_month: int,
    rolling_7: float,
    rolling_30: float,
    trend_slope: float,
    is_festival: bool,
) -> list[float]:
    return [
        float(day_of_week),
        float(day_of_month),
        float(rolling_7),
        float(rolling_30),
        float(trend_slope),
        1.0 if is_festival else 0.0,
    ]


def trend_slope(series: list[float]) -> float:
    """Least-squares slope of the last N points — the demand trend feature."""
    if len(series) < 2:
        return 0.0
    y = np.asarray(series, dtype=float)
    x = np.arange(len(y), dtype=float)
    return float(np.polyfit(x, y, 1)[0])
