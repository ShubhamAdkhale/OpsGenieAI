"""Predictive maintenance assessment (§17).

Division of labour, and why:

* `Machine.health_score` is the stored **state of record**. Seed data and
  simulation events set it. It is not re-derived from sensors on every read,
  because the scripted demo (§7) must produce the same Melt Index every single
  time and a re-derived score would wobble.
* `anomaly_score` / `anomaly_detected` come from a genuinely trained
  IsolationForest over the machine's recent readings. The injected anomalous
  reading in the `refrigeration_degradation` event is far outside the training
  distribution, so this fires reliably.
* `failure_probability` uses a deterministic monotone map from health, so the
  §17 "> 0.75 triggers a maintenance workflow" rule can never mis-fire live.
  It is a CONDITION score - how worn the unit is - and the UI labels it
  "Condition risk". It is not a 24-hour forecast: a worn unit that is barely
  degrading scores high on it and yet will not fail tomorrow.
* `ml_failure_probability` is the trained GradientBoostingClassifier, which
  reads the TREND in the sensor window. It is what the UI shows as
  "Failure < 24h". It informs; the condition rule still decides.
* RUL is a heuristic from the cooling-efficiency decline rate (§17), not a
  fourth model.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Machine, SensorReading

MIN_READINGS_FOR_PREDICTION = 6  # §17 low-confidence fallback
FAILURE_PROBABILITY_ALERT_THRESHOLD = 0.75  # §17
COOLING_EFFICIENCY_CRITICAL_FLOOR = 62.0  # app.ml.synthetic.EFFICIENCY_FLOOR
NOMINAL = {
    "temperature": -18.0,
    "vibration": 2.0,
    "current": 11.0,
    "pressure": 4.2,
    "cooling_efficiency": 95.0,
}
STATUS_BANDS = [(50.0, "CRITICAL"), (80.0, "WARNING")]


def recent_readings(machine: Machine, count: int = 6) -> list[SensorReading]:
    return list(machine.readings)[-count:]


def ml_failure_for(machine: Machine) -> float | None:
    """The classifier's failure-within-24h probability, or None without enough data."""
    from app.ml.registry import predict_failure_probability

    readings = recent_readings(machine, count=12)
    if len(readings) < MIN_READINGS_FOR_PREDICTION:
        return None
    value = predict_failure_probability(readings)
    return None if value is None else round(value, 4)


def status_for(health_score: float) -> str:
    for ceiling, name in STATUS_BANDS:
        if health_score < ceiling:
            return name
    return "HEALTHY"


def failure_probability_for(health_score: float) -> float:
    """Deterministic, monotone, and explainable: a unit at 23% health carries an
    81% chance of failing within 24h. Linear with a small multiplier so a
    genuinely critical unit clears the §17 0.75 action threshold."""
    return round(min(0.99, max(0.0, (100.0 - health_score) / 100.0 * 1.05)), 4)


# Beyond a month, "hours to the floor" stops meaning anything: the estimate is
# a straight-line extrapolation of a near-flat trend. The UI shows "> 30 days".
RUNWAY_CAP_HOURS = 30 * 24.0


def estimate_failure_hours(readings: list[SensorReading], health_score: float) -> float | None:
    """RUL from the rate of decline in cooling efficiency (§17).

    None when the unit is not declining: there is no runway to extrapolate. An
    earlier version invented one from health (health x 1.2 hours), which is how
    a perfectly stable unit came to show "110h" and a slowly drifting one
    "14,814h".
    """
    if len(readings) < 2:
        return None
    first, last = readings[0], readings[-1]
    hours = last.operating_hours - first.operating_hours
    if hours <= 0:
        return None
    slope = (last.cooling_efficiency - first.cooling_efficiency) / hours
    remaining = last.cooling_efficiency - COOLING_EFFICIENCY_CRITICAL_FLOOR
    if remaining <= 0:
        return 0.0
    if slope >= -1e-6:
        return None
    return round(min(RUNWAY_CAP_HOURS, remaining / abs(slope)), 1)


@dataclass
class MachineAssessment:
    anomaly_score: float
    anomaly_detected: bool
    failure_probability: float
    ml_failure_probability: float | None
    estimated_failure_hours: float | None
    status: str
    insufficient_data: bool
    top_risk_factors: list[dict]


def top_risk_factors(readings: list[SensorReading]) -> list[dict]:
    """Rank sensors by how far the latest reading has drifted from nominal."""
    if not readings:
        return []
    latest = readings[-1]
    prior = readings[0]
    factors: list[dict] = []

    eff_drop = NOMINAL["cooling_efficiency"] - latest.cooling_efficiency
    if eff_drop > 1:
        factors.append(
            {
                "factor": "Cooling efficiency",
                "severity": round(min(100.0, eff_drop * 2.0), 1),
                "detail": f"Down {eff_drop:.1f} points from nominal "
                f"({latest.cooling_efficiency:.1f}% vs 95%)",
            }
        )
    vib_ratio = latest.vibration / NOMINAL["vibration"]
    if vib_ratio > 1.2:
        factors.append(
            {
                "factor": "Vibration",
                "severity": round(min(100.0, (vib_ratio - 1) * 100.0), 1),
                "detail": f"{latest.vibration:.2f} mm/s, {vib_ratio:.1f}x nominal",
            }
        )
    current_delta = latest.current - NOMINAL["current"]
    if current_delta > 0.8:
        factors.append(
            {
                "factor": "Current draw",
                "severity": round(min(100.0, current_delta * 18.0), 1),
                "detail": f"{latest.current:.1f} A, {current_delta:.1f} A above nominal "
                "(compressor working harder)",
            }
        )
    temp_delta = latest.temperature - NOMINAL["temperature"]
    if temp_delta > 1.5:
        factors.append(
            {
                "factor": "Internal temperature",
                "severity": round(min(100.0, temp_delta * 12.0), 1),
                "detail": f"{latest.temperature:.1f} C, {temp_delta:.1f} C above the -18 C setpoint",
            }
        )
    eff_trend = latest.cooling_efficiency - prior.cooling_efficiency
    if eff_trend < -2:
        factors.append(
            {
                "factor": "Degradation trend",
                "severity": round(min(100.0, abs(eff_trend) * 3.0), 1),
                "detail": f"Efficiency fell {abs(eff_trend):.1f} points over the last "
                f"{len(readings)} readings",
            }
        )

    factors.sort(key=lambda f: f["severity"], reverse=True)
    return factors[:4]


def assess(machine: Machine) -> MachineAssessment:
    from app.ml.registry import (
        ANOMALY_THRESHOLD,
        predict_anomaly_score,
        predict_failure_probability,
    )

    readings = recent_readings(machine, count=12)
    if len(readings) < MIN_READINGS_FOR_PREDICTION:
        # §17: report insufficient data rather than guessing.
        return MachineAssessment(
            anomaly_score=0.0,
            anomaly_detected=False,
            failure_probability=0.0,
            ml_failure_probability=None,
            estimated_failure_hours=None,
            status="INSUFFICIENT_DATA",
            insufficient_data=True,
            top_risk_factors=top_risk_factors(readings),
        )

    anomaly_score = predict_anomaly_score(readings)
    ml_failure = predict_failure_probability(readings)
    failure_probability = failure_probability_for(machine.health_score)

    return MachineAssessment(
        anomaly_score=round(anomaly_score, 4),
        anomaly_detected=anomaly_score >= ANOMALY_THRESHOLD,
        failure_probability=failure_probability,
        ml_failure_probability=None if ml_failure is None else round(ml_failure, 4),
        estimated_failure_hours=estimate_failure_hours(readings, machine.health_score),
        status=status_for(machine.health_score),
        insufficient_data=False,
        top_risk_factors=top_risk_factors(readings),
    )


def refresh(db: Session, machine: Machine) -> MachineAssessment:
    """Assess and write the derived fields back onto the Machine row."""
    result = assess(machine)
    machine.anomaly_score = result.anomaly_score
    machine.anomaly_detected = result.anomaly_detected
    machine.failure_probability = result.failure_probability
    machine.estimated_failure_hours = result.estimated_failure_hours
    machine.status = result.status
    db.flush()
    return result
