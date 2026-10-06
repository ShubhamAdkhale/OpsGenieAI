"""Train the demand-forecasting model (§16).

    python -m app.ml.train_forecast

One GradientBoostingRegressor per product (§16), all saved into a single
joblib file as a dict keyed by product name, plus a pooled model used as a
fallback for any product the dict does not cover.

THE TRAINING DATA IS SYNTHETIC — 90 days of simulated daily demand per product
from `app/ml/synthetic.demand_series`, with weekly seasonality, a trend, a
weekend lift and a handful of seeded festival dates.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from app.config import settings
from app.ml.features import forecast_features
from app.ml.registry import FORECAST_MODEL
from app.ml.synthetic import demand_series
from app.seed_config import PRODUCTS

RANDOM_STATE = 3
# Days of history needed before the first supervised row can be built.
MIN_HISTORY = 30
# How many synthetic 90-day series to draw per product. One series is far too
# little data for gradient boosting, so we resample the same generator with
# different noise seeds — honest, because the generator IS our ground truth.
SERIES_PER_PRODUCT = 40


def rows_from_series(series: list[dict]) -> tuple[list[list[float]], list[float]]:
    """Turn one daily series into supervised (features, next-day demand) rows."""
    units = [row["units"] for row in series]
    X: list[list[float]] = []
    y: list[float] = []
    for t in range(MIN_HISTORY, len(series)):
        window_7 = units[t - 7 : t]
        window_30 = units[t - 30 : t]
        window_14 = units[t - 14 : t]
        from app.ml.features import trend_slope

        X.append(
            forecast_features(
                day_of_week=t % 7,
                day_of_month=(t % 30) + 1,
                rolling_7=float(np.mean(window_7)),
                rolling_30=float(np.mean(window_30)),
                trend_slope=trend_slope(window_14),
                is_festival=series[t]["is_festival"],
            )
        )
        y.append(units[t])
    return X, y


def build_product_dataset(product: dict) -> tuple[np.ndarray, np.ndarray]:
    X: list[list[float]] = []
    y: list[float] = []
    for i in range(SERIES_PER_PRODUCT):
        series = demand_series(
            base=product["base"],
            weekly_amplitude=product["weekly_amplitude"],
            trend_per_day=product["trend_per_day"],
            noise_sd=product["noise_sd"],
            seed=RANDOM_STATE * 1000 + i,
        )
        sx, sy = rows_from_series(series)
        X.extend(sx)
        y.extend(sy)
    return np.asarray(X, dtype=float), np.asarray(y, dtype=float)


def main() -> int:
    import joblib

    settings.ml_model_dir.mkdir(parents=True, exist_ok=True)
    models: dict[str, GradientBoostingRegressor] = {}
    pooled_X: list[np.ndarray] = []
    pooled_y: list[np.ndarray] = []

    for product in PRODUCTS:
        X, y = build_product_dataset(product)
        # Hold out the last 15% chronologically rather than at random: a
        # forecaster evaluated on shuffled days is grading itself too kindly.
        split = int(len(X) * 0.85)
        model = GradientBoostingRegressor(
            n_estimators=200, max_depth=3, learning_rate=0.07, random_state=RANDOM_STATE
        )
        model.fit(X[:split], y[:split])
        mae = mean_absolute_error(y[split:], model.predict(X[split:]))
        baseline_mae = mean_absolute_error(y[split:], X[split:, 2])  # rolling_7 as baseline
        print(
            f"[forecast] {product['name']:<16} rows={len(X):>5} "
            f"MAE={mae:7.2f} units (7-day-average baseline {baseline_mae:7.2f})"
        )
        # Sanity check (§32): the model must beat a plain 7-day moving average,
        # otherwise there is no reason to ship it.
        assert mae < baseline_mae, f"{product['name']}: model did not beat the moving average"
        models[product["name"]] = model
        pooled_X.append(X)
        pooled_y.append(y)

    X_all = np.vstack(pooled_X)
    y_all = np.concatenate(pooled_y)
    pooled = GradientBoostingRegressor(
        n_estimators=200, max_depth=3, learning_rate=0.07, random_state=RANDOM_STATE
    )
    pooled.fit(X_all, y_all)
    print(f"[forecast] pooled fallback model trained on {len(X_all)} rows")

    joblib.dump({"per_product": models, "pooled": pooled}, settings.ml_model_dir / FORECAST_MODEL)
    print(f"[forecast] saved {FORECAST_MODEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
