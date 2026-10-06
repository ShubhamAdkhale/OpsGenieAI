"""Synthetic data generators.

EVERYTHING produced here is simulated. None of it is real company data, real
IoT telemetry, or a real demand history, and the UI says so on screen (§29).
The generators live here rather than in `seed.py` so the training scripts and
the seed data are guaranteed to come from the same distribution (§15).

All generators are seeded, so a rebuild produces byte-identical data — which is
what makes the scripted demo repeatable (§38).
"""

from __future__ import annotations

import numpy as np

from app.ml.features import reading

NOMINAL_EFFICIENCY = 95.0
# Below this, the unit can no longer hold a frozen setpoint — the target of the
# RUL heuristic in `services/maintenance.py`.
EFFICIENCY_FLOOR = 62.0

# Linear, invertible map between health score and cooling efficiency, so
# "health 23%" and "efficiency 68%" can never tell contradictory stories.
#
# The slope is CALIBRATED: the scripted `refrigeration_degradation` event drops
# RF-204's efficiency by 18 points (the "-18%" in §7 step 3), and that same
# event must drop its health by the 51 points the §7 Melt Index arc needs.
# 18 / 51 is therefore the conversion rate, not an arbitrary constant.
EFFICIENCY_PER_HEALTH_POINT = 18.0 / 51.0


def efficiency_for_health(health: float) -> float:
    return NOMINAL_EFFICIENCY - (100.0 - float(health)) * EFFICIENCY_PER_HEALTH_POINT


def health_for_efficiency(efficiency: float) -> float:
    return 100.0 - (NOMINAL_EFFICIENCY - float(efficiency)) / EFFICIENCY_PER_HEALTH_POINT


def sensors_for_efficiency(efficiency: float, rng: np.random.Generator | None = None) -> dict:
    """Physics-flavoured (not physics-accurate) sensor values for an efficiency.

    As a reefer loses cooling capacity: box temperature rises, the compressor
    vibrates more, it draws more current, and suction pressure falls.
    """
    drop = NOMINAL_EFFICIENCY - float(efficiency)
    noise = (lambda s: float(rng.normal(0, s))) if rng is not None else (lambda s: 0.0)
    return {
        "temperature": round(-18.0 + drop * 0.50 + noise(0.25), 2),
        "vibration": round(max(0.2, 2.0 + drop * 0.13 + noise(0.06)), 3),
        "current": round(max(1.0, 11.0 + drop * 0.17 + noise(0.10)), 3),
        "pressure": round(max(0.5, 4.2 - drop * 0.045 + noise(0.04)), 3),
        "cooling_efficiency": round(float(efficiency) + noise(0.15), 2),
    }


# ---------------------------------------------------------------------------
# Sensor history for seeding
# ---------------------------------------------------------------------------


def sensor_history(
    end_health: float,
    count: int = 50,
    hours_step: float = 4.0,
    decline_span: float | None = None,
    seed: int = 0,
) -> list[dict]:
    """A trailing history that lands exactly on `end_health`.

    Healthier machines get a nearly flat trace; degrading ones get a visible
    downward slope, which is what makes the trend chart on the Predictive
    Maintenance page worth looking at.
    """
    rng = np.random.default_rng(seed)
    end_eff = efficiency_for_health(end_health)
    if decline_span is None:
        # The worse the unit, the steeper the recent decline.
        decline_span = float(np.interp(end_health, [0, 50, 80, 100], [9.0, 6.0, 2.0, 0.5]))
    start_eff = min(NOMINAL_EFFICIENCY, end_eff + decline_span)

    rows: list[dict] = []
    for i in range(count):
        frac = i / max(count - 1, 1)
        efficiency = start_eff + (end_eff - start_eff) * frac
        values = sensors_for_efficiency(efficiency, rng)
        values["operating_hours"] = round(i * hours_step, 2)
        rows.append(values)
    return rows


def anomalous_reading(efficiency: float, operating_hours: float, seed: int = 42) -> dict:
    """The out-of-distribution reading injected by `refrigeration_degradation`.

    It is deliberately far outside the normal-operation envelope the
    IsolationForest was trained on, so the anomaly detector fires reliably
    during the live demo instead of "usually".
    """
    rng = np.random.default_rng(seed)
    values = sensors_for_efficiency(efficiency, rng)
    values["vibration"] = round(values["vibration"] * 1.35, 3)
    values["current"] = round(values["current"] * 1.15, 3)
    values["operating_hours"] = round(operating_hours, 2)
    return values


# ---------------------------------------------------------------------------
# Degradation trajectories for training the maintenance models (§17)
# ---------------------------------------------------------------------------


def operation_windows(
    n_units: int, fault_rate: tuple[float, float] | None = None, seed: int = 7
) -> list[list]:
    """Six-reading windows for the anomaly detector, one per unit.

    With `fault_rate=None` every unit is in NORMAL operation: baseline wear only,
    at any efficiency from nearly failed to new, at any reading cadence from
    0.2 to 5 hours. That breadth is the point. The first detector was trained
    on healthy units read every 2-5 hours, so once the live tick started
    writing a reading every 12 minutes, every worn-but-stable unit looked
    abnormal: six of twelve were flagged within a minute, with nothing wrong.

    With `fault_rate=(lo, hi)` each unit is losing efficiency at a log-uniform
    rate in that range (points/hour) - used to measure what the detector catches.
    """
    rng = np.random.default_rng(seed)
    windows: list[list] = []
    for _ in range(n_units):
        hours_step = float(np.exp(rng.uniform(np.log(0.2), np.log(5.0))))
        hours_offset = float(rng.uniform(0.0, 3000.0))
        if fault_rate is None:
            rate = float(rng.uniform(0.0, 0.05))
        else:
            rate = float(np.exp(rng.uniform(np.log(fault_rate[0]), np.log(fault_rate[1]))))
        span = 5 * hours_step
        # Start high enough that the window does not run into the clamp.
        low = EFFICIENCY_FLOOR - 15.0 + rate * span
        efficiency = float(rng.uniform(min(low, NOMINAL_EFFICIENCY - 1.0), NOMINAL_EFFICIENCY))
        readings = []
        for step in range(6):
            eff = efficiency - rate * step * hours_step + float(rng.normal(0, 0.1))
            values = sensors_for_efficiency(eff, rng)
            readings.append(reading(operating_hours=hours_offset + step * hours_step, **values))
        windows.append(readings)
    return windows


def failure_trajectories(
    n_trajectories: int = 900, length: int = 70, seed: int = 11
) -> tuple[list[list], list[int], list[int], list[bool]]:
    """Training data for the failure-within-24h classifier.

    The first classifier was trained on a generic degradation generator that
    was a poor fit, for four reasons that each showed up as a wrong answer in
    the live demo:

      * windows AFTER the failure point were labelled 0, so the model learnt
        that a unit already below the efficiency floor was safe - it said 0.3%
        for RF-204 at 1% health;
      * its fastest decay was ~0.8 points/h, while a refrigerant leak in the
        simulation runs at 5 points/h - an order of magnitude outside training;
      * readings were 2-5 h apart, while the live tick writes one every 12-30
        min, so every rate-of-change feature came from a different regime;
      * operating hours stopped at ~300, the fleet runs at 200-3,000.

    This generator covers the regimes the simulation actually produces: slow
    baseline wear, stable-but-degraded units, fast leaks, accelerating decay,
    repairs that restore efficiency, and reading cadences from 0.2 to 5 hours.

    The label is "already below the efficiency floor, or will reach it within
    the next 24 hours" - a failed unit is the most certain failure there is.

    Returns `(windows, labels, groups, observable)`. `groups` is the trajectory
    index, so a held-out split can keep every window of one unit on the same
    side. `observable` is False for a positive whose fault has not STARTED by the
    end of the window: no sensor model can see a leak that has not happened
    yet, so those windows set the ceiling on achievable accuracy.
    """
    rng = np.random.default_rng(seed)
    windows: list[list] = []
    labels: list[int] = []
    groups: list[int] = []
    observable: list[bool] = []
    floor_min = EFFICIENCY_FLOOR - 17.0  # the live simulation bottoms out at floor - 12

    for traj in range(n_trajectories):
        # Log-uniform cadence: many short-interval (live tick) and long-interval
        # (seeded history) units.
        hours_step = float(np.exp(rng.uniform(np.log(0.2), np.log(5.0))))
        hours_offset = float(rng.uniform(0.0, 3000.0))
        efficiency = float(rng.uniform(EFFICIENCY_FLOOR + 2.0, NOMINAL_EFFICIENCY))
        base_wear = float(rng.uniform(0.005, 0.05))

        faulty = bool(rng.random() < 0.55)
        fault_start = float(rng.uniform(0.0, length * hours_step)) if faulty else np.inf
        # Log-uniform fault severity: slow drift up to an acute refrigerant leak.
        fault_rate = float(np.exp(rng.uniform(np.log(0.1), np.log(8.0))))
        acceleration = float(rng.uniform(0.0, 0.05))
        repaired_at = (
            fault_start + float(rng.uniform(2.0, 30.0))
            if faulty and rng.random() < 0.3
            else np.inf
        )

        # Integrate on a fine grid so the label can look 24 h ahead exactly,
        # then sample readings at this unit's cadence.
        horizon_h = length * hours_step + 24.0
        dt = min(0.1, hours_step)
        n_fine = int(np.ceil(horizon_h / dt)) + 1
        eff_path = np.empty(n_fine)
        eff = efficiency
        for i in range(n_fine):
            t = i * dt
            if t >= repaired_at and t - dt < repaired_at:
                eff = float(rng.uniform(85.0, NOMINAL_EFFICIENCY))
            rate = base_wear
            if fault_start <= t < repaired_at:
                rate += fault_rate * (1.0 + acceleration * (t - fault_start))
            eff = max(floor_min, min(NOMINAL_EFFICIENCY, eff - rate * dt))
            eff_path[i] = eff

        readings: list = []
        for step in range(length):
            t = step * hours_step
            eff_now = float(eff_path[int(round(t / dt))]) + float(rng.normal(0, 0.1))
            values = sensors_for_efficiency(eff_now, rng)
            readings.append(reading(operating_hours=hours_offset + t, **values))

        for step in range(5, length):
            t = step * hours_step
            i_now = int(round(t / dt))
            i_24h = min(n_fine - 1, int(round((t + 24.0) / dt)))
            fails = bool((eff_path[i_now : i_24h + 1] <= EFFICIENCY_FLOOR).any())
            windows.append(readings[step - 5 : step + 1])
            labels.append(1 if fails else 0)
            groups.append(traj)
            already_below = bool(eff_path[i_now] <= EFFICIENCY_FLOOR)
            observable.append(not fails or already_below or fault_start <= t)

    return windows, labels, groups, observable


# ---------------------------------------------------------------------------
# Demand history for the forecasting model (§16)
# ---------------------------------------------------------------------------

# Seeded Indian festival offsets (days before "today") for the is_festival flag.
FESTIVAL_DAY_OFFSETS = (78, 62, 41, 33, 17, 9)


def demand_series(
    base: float,
    weekly_amplitude: float,
    trend_per_day: float,
    noise_sd: float,
    festival_multiplier: float = 1.6,
    days: int = 90,
    seed: int = 0,
) -> list[dict]:
    """90 days of daily demand with weekly seasonality, trend and festivals."""
    rng = np.random.default_rng(seed)
    festivals = set(days - 1 - o for o in FESTIVAL_DAY_OFFSETS)
    rows: list[dict] = []
    for day_index in range(days):
        weekday = day_index % 7
        seasonal = weekly_amplitude * np.sin(2 * np.pi * (weekday / 7.0))
        # Weekend retail lift.
        weekend = base * 0.12 if weekday in (5, 6) else 0.0
        is_festival = day_index in festivals
        units = (
            base
            + seasonal
            + weekend
            + trend_per_day * day_index
            + float(rng.normal(0, noise_sd))
        )
        if is_festival:
            units *= festival_multiplier
        rows.append(
            {
                "day_index": day_index,
                "units": round(max(0.0, units), 1),
                "is_festival": is_festival,
            }
        )
    return rows
