"""Train the spoilage classifier (§19).

    python -m app.ml.train_spoilage

Labels come from a rule-based simulator: a shipment is labelled "spoiled" when
its cumulative temperature-time exposure — proxied by the §18 Melt Index —
clears a product-specific threshold, with Bernoulli noise so the classifier
learns a probability rather than a step function.

THE TRAINING DATA IS SYNTHETIC. Note also that the running app defaults to the
deterministic calibrated curve rather than this model
(`USE_ML_SPOILAGE=false`) so the live demo numbers are byte-reproducible; see
`services/risk_engine.spoilage_from_melt_index`.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split

from app.config import settings
from app.ml.registry import SPOILAGE_MODEL
from app.services.risk_engine import WEIGHTS, spoilage_from_melt_index

RANDOM_STATE = 11
N_SAMPLES = 12_000
SHELF_LIFE_CHOICES = (18.0, 24.0, 36.0, 48.0)


def build_dataset(n: int = N_SAMPLES) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(RANDOM_STATE)

    # Sample the six §18 components over their full 0..100 range.
    temperature = rng.uniform(0, 100, n)
    refrigeration = rng.uniform(0, 100, n)
    traffic = rng.uniform(0, 100, n)
    weather = rng.choice([0.0, 40.0, 70.0, 100.0], n)
    shelf_life = rng.uniform(0, 100, n)
    eta = rng.uniform(0, 100, n)

    melt = (
        WEIGHTS["temperature"] * temperature
        + WEIGHTS["refrigeration"] * refrigeration
        + WEIGHTS["traffic"] * traffic
        + WEIGHTS["weather"] * weather
        + WEIGHTS["shelf_life"] * shelf_life
        + WEIGHTS["eta"] * eta
    )

    shelf_hours = rng.choice(SHELF_LIFE_CHOICES, n)
    value_lakh = rng.uniform(1.0, 6.0, n)

    # A shorter-shelf-life product spoils at a lower exposure, so nudge the
    # curve's midpoint by product fragility before sampling the label.
    fragility = (36.0 - shelf_hours) * 0.15
    probability = np.asarray(
        [spoilage_from_melt_index(m + f) for m, f in zip(melt, fragility, strict=True)]
    )
    y = (rng.uniform(0, 1, n) < probability).astype(int)

    X = np.column_stack(
        [temperature, refrigeration, traffic, weather, shelf_life, eta, value_lakh, shelf_hours]
    )
    return X, y, probability


def main() -> int:
    import joblib

    settings.ml_model_dir.mkdir(parents=True, exist_ok=True)
    X, y, true_p = build_dataset()
    print(f"[spoilage] dataset: {X.shape[0]} rows, {y.mean() * 100:.1f}% spoiled")

    X_train, X_test, y_train, y_test, _, p_test = train_test_split(
        X, y, true_p, test_size=0.25, random_state=RANDOM_STATE, stratify=y
    )
    clf = GradientBoostingClassifier(
        n_estimators=220, max_depth=3, learning_rate=0.06, random_state=RANDOM_STATE
    )
    clf.fit(X_train, y_train)
    probs = clf.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, probs)
    brier = brier_score_loss(y_test, probs)

    # The labels are Bernoulli draws from a probability, so no classifier can
    # reach AUC 1.0 here — the noise ceiling is what the TRUE probability
    # itself scores. Grading against an absolute threshold would be measuring
    # the label noise, not the model, so we grade against that oracle instead.
    oracle_auc = roc_auc_score(y_test, p_test)
    oracle_brier = brier_score_loss(y_test, p_test)
    print(
        f"[spoilage] held-out ROC AUC {auc:.3f} (oracle ceiling {oracle_auc:.3f}), "
        f"Brier {brier:.4f} (oracle {oracle_brier:.4f})"
    )
    print(f"[spoilage] recovered {auc / oracle_auc * 100:.1f}% of the achievable AUC")
    assert auc > 0.95 * oracle_auc, (
        f"spoilage AUC {auc:.3f} is more than 5% below the {oracle_auc:.3f} noise ceiling"
    )
    # Calibration matters more than ranking here, since the probability is
    # multiplied by the shipment value to produce a rupee figure.
    assert brier < oracle_brier * 1.05, (
        f"spoilage Brier {brier:.4f} is poorly calibrated vs the {oracle_brier:.4f} ceiling"
    )
    joblib.dump(clf, settings.ml_model_dir / SPOILAGE_MODEL)
    print(f"[spoilage] saved {SPOILAGE_MODEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
