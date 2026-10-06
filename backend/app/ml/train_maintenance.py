"""Train the predictive-maintenance models (§17).

    python -m app.ml.train_maintenance

Two models are produced:

* IsolationForest over NORMAL-OPERATION windows only, looking at the sensors'
  RATES OF CHANGE (a pipeline selects those columns). Normal covers every wear
  level and every reading cadence, so a worn-but-steady unit is normal and a
  unit that starts drifting is not. Evaluated on its false-alarm rate on
  held-out normal units and its detection rate by fault speed.
* GradientBoostingClassifier for "failed, or will fail within 24h", trained on
  `failure_trajectories` - see that function for why it has its own generator.
  It is evaluated on held-out TRAJECTORIES (never a window from a unit it
  trained on) and against the health rule the product actually acts on.

THE TRAINING DATA IS SYNTHETIC. It comes from a physics-inspired decay curve
with noise in `app/ml/synthetic.py`, not from real refrigeration telemetry.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer

from app.config import settings
from app.ml.features import maintenance_features, rate_columns
from app.ml.registry import (
    ANOMALY_MODEL,
    ANOMALY_THRESHOLD,
    FAILURE_MODEL,
    anomaly_score_from_decision,
)
from app.ml.synthetic import (
    failure_trajectories,
    health_for_efficiency,
    operation_windows,
)

RANDOM_STATE = 7


def features_of(windows: list[list]) -> np.ndarray:
    return np.asarray([maintenance_features(w) for w in windows], dtype=float)


def flagged_share(model, X: np.ndarray) -> float:
    """Share of windows the app would report as "anomaly detected"."""
    scores = np.asarray([anomaly_score_from_decision(d) for d in model.decision_function(X)])
    return float((scores >= ANOMALY_THRESHOLD).mean())


def build_failure_dataset() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    windows, labels, groups, observable = failure_trajectories(seed=RANDOM_STATE)
    X = np.asarray([maintenance_features(w) for w in windows], dtype=float)
    return (
        X,
        np.asarray(labels, dtype=int),
        np.asarray(groups, dtype=int),
        np.asarray(observable, dtype=bool),
    )


def health_rule(X: np.ndarray) -> np.ndarray:
    """The deterministic map `services/maintenance.py` acts on, as a baseline."""
    from app.services.maintenance import failure_probability_for

    efficiency = X[:, 4]
    return np.asarray(
        [failure_probability_for(max(1.0, min(100.0, health_for_efficiency(e)))) for e in efficiency]
    )


def main() -> int:
    import joblib

    settings.ml_model_dir.mkdir(parents=True, exist_ok=True)
    # --- anomaly detector -------------------------------------------------
    X_normal = features_of(operation_windows(6000, seed=RANDOM_STATE))
    iso = make_pipeline(
        FunctionTransformer(rate_columns),
        IsolationForest(n_estimators=200, contamination=0.01, random_state=RANDOM_STATE),
    )
    iso.fit(X_normal)
    held_out_normal = features_of(operation_windows(2000, seed=RANDOM_STATE + 1))
    false_alarms = flagged_share(iso, held_out_normal)
    print(f"[maintenance] anomaly detector: {false_alarms * 100:.1f}% false alarms on held-out normal units")
    detection = {}
    for lo, hi in ((0.3, 1.0), (1.0, 3.0), (3.0, 10.0)):
        faults = features_of(operation_windows(1000, fault_rate=(lo, hi), seed=RANDOM_STATE + 2))
        detection[(lo, hi)] = flagged_share(iso, faults)
        print(
            f"[maintenance]   detects {detection[(lo, hi)] * 100:5.1f}% of units losing "
            f"{lo:g}-{hi:g} pts/h"
        )
    assert false_alarms < 0.03, f"false-alarm rate {false_alarms:.1%} above 3%"
    assert detection[(3.0, 10.0)] > 0.95, "misses fast faults like a refrigerant leak"
    joblib.dump(iso, settings.ml_model_dir / ANOMALY_MODEL)
    print(f"[maintenance] saved {ANOMALY_MODEL}")

    # --- failure-within-24h classifier ------------------------------------
    Xf, yf, groups, observable = build_failure_dataset()
    print(
        f"[maintenance] failure dataset: {Xf.shape[0]} windows from "
        f"{len(np.unique(groups))} trajectories, {yf.mean() * 100:.1f}% positive"
    )
    split = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=RANDOM_STATE)
    train_idx, test_idx = next(split.split(Xf, yf, groups))
    clf = GradientBoostingClassifier(
        n_estimators=250, max_depth=3, learning_rate=0.08, subsample=0.8,
        random_state=RANDOM_STATE,
    )
    clf.fit(Xf[train_idx], yf[train_idx])
    probs = clf.predict_proba(Xf[test_idx])[:, 1]
    y_test = yf[test_idx]
    auc = roc_auc_score(y_test, probs)
    brier = brier_score_loss(y_test, probs)
    rule = health_rule(Xf[test_idx])
    rule_auc = roc_auc_score(y_test, rule)
    rule_brier = brier_score_loss(y_test, rule)
    print(
        f"[maintenance] failure classifier, held-out trajectories: ROC AUC {auc:.3f}, "
        f"Brier {brier:.3f}"
    )
    print(
        f"[maintenance] health-rule baseline on the same windows: ROC AUC {rule_auc:.3f}, "
        f"Brier {rule_brier:.3f}"
    )
    # The honest ceiling: a positive whose fault has not begun by the end of the
    # window is invisible to ANY sensor model. Scoring on the observable windows
    # measures what the model can actually be held to.
    seen = observable[test_idx]
    unseen_share = 1.0 - seen[y_test == 1].mean()
    obs_auc = roc_auc_score(y_test[seen], probs[seen])
    obs_rule_auc = roc_auc_score(y_test[seen], rule[seen])
    print(
        f"[maintenance] {unseen_share * 100:.1f}% of held-out positives are faults that start "
        f"after the window (unforecastable by any sensor model)"
    )
    print(
        f"[maintenance] on observable windows: classifier ROC AUC {obs_auc:.3f} "
        f"vs health rule {obs_rule_auc:.3f}"
    )
    assert obs_auc > 0.95, f"observable-window AUC {obs_auc:.3f} below the 0.95 floor"
    assert auc > rule_auc, "classifier does not beat the health rule it is meant to second-guess"
    joblib.dump(clf, settings.ml_model_dir / FAILURE_MODEL)
    print(f"[maintenance] saved {FAILURE_MODEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
