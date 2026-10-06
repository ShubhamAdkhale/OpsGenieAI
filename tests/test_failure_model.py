"""The failure-within-24h classifier: what it is trained on, and what it says live.

The previous model reported 0.3% failure risk for RF-204 at 1% health - the
climax of the demo - because windows after the failure point were labelled
negative and the live leak ran ten times faster than anything it trained on.
These tests pin both fixes down.
"""

from __future__ import annotations

import pytest

from app.ml.features import maintenance_features
from app.ml.registry import model_status
from app.ml.synthetic import EFFICIENCY_FLOOR, failure_trajectories
from app.models import Machine
from app.services import maintenance
from app.simulation import engine


def test_a_unit_already_below_the_floor_is_labelled_as_failing():
    windows, labels, _, _ = failure_trajectories(n_trajectories=60, seed=3)
    below = [
        label
        for window, label in zip(windows, labels)
        if maintenance_features(window)[4] < EFFICIENCY_FLOOR - 3.0
    ]
    assert below, "generator produced no failed units to check"
    assert all(label == 1 for label in below)


def test_training_covers_the_rates_the_live_simulation_produces():
    # The refrigerant leak runs at ~5 points/h; the old generator topped out at 0.8.
    windows, _, _, _ = failure_trajectories(n_trajectories=150, seed=5)
    rates = [maintenance_features(w)[10] for w in windows]
    assert min(rates) < -5.0


def _ml(db, code):
    machine = db.query(Machine).filter(Machine.code == code).one()
    return maintenance.assess(machine).ml_failure_probability


@pytest.mark.skipif(
    not model_status().get("maintenance_failure_gbc.joblib", {}).get("loaded"),
    reason="trained failure model not present - run python -m app.ml.train_all",
)
def test_the_classifier_tracks_the_demo_arc(db):
    engine.reset(db)
    assert _ml(db, "RF-204") < 0.2
    assert _ml(db, "RF-201") < 0.1

    engine.trigger_event(db, "refrigeration_degradation")
    assert _ml(db, "RF-204") > 0.75  # leaking fast: failing within 24h

    engine.trigger_event(db, "weather_deterioration")
    assert _ml(db, "RF-204") > 0.9  # below the floor: failed
    assert _ml(db, "RF-201") < 0.1  # the heat alone does not fail a healthy unit

    engine.trigger_event(db, "maintenance_completed")
    assert _ml(db, "RF-204") < 0.2  # repaired
