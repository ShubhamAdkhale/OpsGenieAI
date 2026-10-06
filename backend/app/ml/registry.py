"""Lazy model loading with a deterministic fallback for every prediction (§33).

Golden rule: nothing in this file may raise. If a model file is missing, stale,
or throws, the caller gets `None` and uses its own rule-based fallback. The
demo must never die because of ML (§38).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from app.config import settings
from app.ml.features import maintenance_features, spoilage_features

MODEL_DIR: Path = settings.ml_model_dir

FORECAST_MODEL = "forecast_gbr.joblib"
ANOMALY_MODEL = "maintenance_isolation_forest.joblib"
FAILURE_MODEL = "maintenance_failure_gbc.joblib"
SPOILAGE_MODEL = "spoilage_gbc.joblib"

_cache: dict[str, Any] = {}
_load_errors: dict[str, str] = {}


def _load(name: str) -> Any | None:
    if name in _cache:
        return _cache[name]
    path = MODEL_DIR / name
    try:
        import joblib

        model = joblib.load(path)
    except Exception as exc:  # noqa: BLE001 — never let ML break the API
        _load_errors[name] = f"{type(exc).__name__}: {exc}"
        _cache[name] = None
        return None
    _cache[name] = model
    return model


def model_status() -> dict:
    """Surfaced on /api/health so you can see at a glance whether the demo is
    running on models or on fallbacks."""
    out = {}
    for name in (FORECAST_MODEL, ANOMALY_MODEL, FAILURE_MODEL, SPOILAGE_MODEL):
        loaded = _load(name) is not None
        out[name] = {
            "loaded": loaded,
            "path": str(MODEL_DIR / name),
            "error": _load_errors.get(name),
        }
    return out


def reset_cache() -> None:
    _cache.clear()
    _load_errors.clear()


# ---------------------------------------------------------------------------
# Predictive maintenance
# ---------------------------------------------------------------------------


# A score at or above this is reported as "anomaly detected".
ANOMALY_THRESHOLD = 0.6


def anomaly_score_from_decision(decision: float) -> float:
    """Squash IsolationForest's signed decision function into 0..1 (higher = stranger)."""
    return max(0.0, min(1.0, 1.0 / (1.0 + math.exp(12.0 * float(decision)))))


def predict_anomaly_score(readings: list) -> float:
    """0..1, higher = more anomalous. Falls back to a rate-of-decline rule.

    Both paths judge BEHAVIOUR - how fast the sensors are moving - not level:
    a unit that is worn but steady is a condition-risk matter, not an anomaly.
    """
    features = maintenance_features(readings)
    model = _load(ANOMALY_MODEL)
    if model is not None:
        try:
            return anomaly_score_from_decision(model.decision_function([features])[0])
        except Exception:  # noqa: BLE001
            pass
    # Fallback: how fast cooling efficiency is falling (2 points/hour -> 1.0).
    efficiency_rate = features[-1] if features else 0.0
    return max(0.0, min(1.0, -efficiency_rate / 2.0))


def predict_failure_probability(readings: list) -> float | None:
    """The trained classifier's own opinion, reported for transparency.

    The number the §17 action threshold actually uses is the deterministic map
    in `services/maintenance.py` — see that module's docstring for why.
    """
    model = _load(FAILURE_MODEL)
    if model is None:
        return None
    try:
        features = maintenance_features(readings)
        return float(model.predict_proba([features])[0][1])
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Spoilage
# ---------------------------------------------------------------------------


def predict_spoilage(components, shipment) -> float | None:
    model = _load(SPOILAGE_MODEL)
    if model is None:
        return None
    try:
        features = spoilage_features(
            components,
            shipment.shipment_value_inr,
            shipment.product.unit_shelf_life_hours,
        )
        return float(model.predict_proba([features])[0][1])
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Demand forecast
# ---------------------------------------------------------------------------


def predict_demand(features: list[float], product_name: str | None = None) -> float | None:
    """§16 trains one regressor per product; the pooled model is the fallback
    for any product name the bundle does not know about."""
    bundle = _load(FORECAST_MODEL)
    if bundle is None:
        return None
    try:
        model = None
        if isinstance(bundle, dict):
            if product_name is not None:
                model = bundle.get("per_product", {}).get(product_name)
            model = model or bundle.get("pooled")
        else:  # a bare estimator, e.g. from an older model file
            model = bundle
        if model is None:
            return None
        return float(model.predict([features])[0])
    except Exception:  # noqa: BLE001
        return None
