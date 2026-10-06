"""Demand forecast, projected inventory and reorder recommendation (§16)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app.ml.features import forecast_features, trend_slope
from app.ml.registry import predict_demand
from app.models import DemandHistory, Forecast, Inventory, Product

HORIZON_DAYS = 7
MIN_HISTORY_DAYS = 14  # §16 low-confidence fallback threshold
SAFETY_STOCK_FRACTION = 0.15
# Stockout probability is a logistic on demand-to-stock ratio: at ratio 1.0
# (demand exactly equals stock) it reads 50%, which is the honest answer.
STOCKOUT_STEEPNESS = 4.0


@dataclass
class ProductForecast:
    product_id: int
    product_name: str
    category: str
    period_label: str
    historical_demand: float
    predicted_demand: float
    current_stock: float
    projected_inventory: float
    stockout_probability: float
    recommended_reorder_qty: float
    model_source: str
    warehouse_city: str
    daily: list[dict]

    def to_payload(self) -> dict:
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "category": self.category,
            "period_label": self.period_label,
            "historical_demand": round(self.historical_demand, 1),
            "predicted_demand": round(self.predicted_demand, 1),
            "current_stock": round(self.current_stock, 1),
            "projected_inventory": round(self.projected_inventory, 1),
            "stockout_probability": round(self.stockout_probability, 4),
            "recommended_reorder_qty": round(self.recommended_reorder_qty),
            "model_source": self.model_source,
            "warehouse_city": self.warehouse_city,
            "daily": self.daily,
        }


def stockout_probability(predicted_demand: float, current_stock: float) -> float:
    ratio = predicted_demand / max(current_stock, 1.0)
    return 1.0 / (1.0 + math.exp(-STOCKOUT_STEEPNESS * (ratio - 1.0)))


def _moving_average_forecast(units: list[float]) -> tuple[list[float], str]:
    """§16 fallback: a plain 7-day moving average, used when there is too
    little history to trust a learned model — or when the model is missing."""
    window = units[-7:] or [0.0]
    daily = float(np.mean(window))
    return [daily] * HORIZON_DAYS, "moving_average_7d"


def forecast_product(db: Session, product: Product) -> ProductForecast:
    history = (
        db.query(DemandHistory)
        .filter(DemandHistory.product_id == product.id)
        .order_by(DemandHistory.day)
        .all()
    )
    units = [float(h.units) for h in history]
    inventory = (
        db.query(Inventory).filter(Inventory.product_id == product.id).one_or_none()
    )
    current_stock = float(inventory.current_stock) if inventory else 0.0

    if len(units) < MIN_HISTORY_DAYS:
        predictions, source = _moving_average_forecast(units)
    else:
        predictions, source = _model_forecast(units, product)

    predicted_total = float(sum(predictions))
    historical_total = float(sum(units[-HORIZON_DAYS:])) if units else 0.0
    projected = current_stock - predicted_total
    shortfall = max(0.0, predicted_total - current_stock)
    reorder = math.ceil(shortfall * (1.0 + SAFETY_STOCK_FRACTION)) if shortfall > 0 else 0.0

    # Day-by-day series for the chart: trailing history plus the forecast.
    daily: list[dict] = []
    tail = units[-21:]
    offset = len(units) - len(tail)
    for i, value in enumerate(tail):
        daily.append({"label": f"D-{len(tail) - i}", "actual": round(value, 1), "forecast": None})
    for i, value in enumerate(predictions):
        daily.append({"label": f"D+{i + 1}", "actual": None, "forecast": round(value, 1)})
    del offset

    return ProductForecast(
        product_id=product.id,
        product_name=product.name,
        category=product.category,
        period_label=f"Next {HORIZON_DAYS} days",
        historical_demand=historical_total,
        predicted_demand=predicted_total,
        current_stock=current_stock,
        projected_inventory=projected,
        stockout_probability=stockout_probability(predicted_total, current_stock),
        recommended_reorder_qty=reorder,
        model_source=source,
        warehouse_city=inventory.warehouse_city if inventory else "-",
        daily=daily,
    )


def _model_forecast(units: list[float], product: Product) -> tuple[list[float], str]:
    """Recursive multi-step forecast: predict a day, append it, roll forward."""
    series = list(units)
    predictions: list[float] = []
    for step in range(HORIZON_DAYS):
        t = len(series)
        features = forecast_features(
            day_of_week=t % 7,
            day_of_month=(t % 30) + 1,
            rolling_7=float(np.mean(series[-7:])),
            rolling_30=float(np.mean(series[-30:])),
            trend_slope=trend_slope(series[-14:]),
            is_festival=False,  # no festival known inside the forecast horizon
        )
        value = predict_demand(features, product_name=product.name)
        if value is None:
            # §33: model missing or errored — fall back for the whole horizon so
            # the numbers stay internally consistent.
            return _moving_average_forecast(units)
        value = max(0.0, value)
        predictions.append(value)
        series.append(value)
        del step
    return predictions, "gradient_boosting"


def refresh_forecasts(db: Session) -> list[ProductForecast]:
    """Recompute and persist a Forecast row per product."""
    results: list[ProductForecast] = []
    for product in db.query(Product).order_by(Product.id).all():
        result = forecast_product(db, product)
        row = (
            db.query(Forecast)
            .filter(Forecast.product_id == product.id)
            .order_by(Forecast.id.desc())
            .first()
        )
        if row is None:
            row = Forecast(product_id=product.id)
            db.add(row)
        row.period_label = result.period_label
        row.historical_demand = result.historical_demand
        row.predicted_demand = result.predicted_demand
        row.projected_inventory = result.projected_inventory
        row.stockout_probability = result.stockout_probability
        row.recommended_reorder_qty = result.recommended_reorder_qty
        row.model_source = result.model_source
        results.append(result)
    db.flush()
    return results
