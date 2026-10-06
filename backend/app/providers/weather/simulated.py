"""The terminal weather provider: always answers, never claims to be live.

Not a weather model - a plausible day/night sine around a per-latitude mean, so
the thermal model still has a moving ambient to integrate against when
Open-Meteo is unreachable. It is deterministic in the SIMULATED clock rather
than the wall clock, which is what lets the demo be re-run and the tests assert
exact values without touching the network.
"""

from __future__ import annotations

import math
from typing import Sequence

from app.providers.base import SIMULATED_FALLBACK, FetchContext
from app.providers.weather.model import Waypoint, classify


class SimulatedWeatherProvider:
    stream = "weather"
    source = SIMULATED_FALLBACK

    @property
    def enabled(self) -> bool:
        # Never disabled. A chain whose terminal provider can switch itself off
        # has states in which it returns nothing at all.
        return True

    def one(self, waypoint: Waypoint, sim_minutes: float) -> dict:
        hour = (sim_minutes / 60.0) % 24.0
        # Peak around 15:00, trough around 03:00.
        diurnal = math.sin((hour - 9.0) / 24.0 * 2.0 * math.pi)
        mean_c = 31.0 - (waypoint.lat - 19.0) * 0.25
        temperature = mean_c + diurnal * 5.5
        humidity = 62.0 - diurnal * 12.0
        return {
            "temperature_c": round(temperature, 2),
            "humidity_pct": round(humidity, 1),
            "precipitation_mm": 0.0,
            "wind_kph": round(12.0 + abs(diurnal) * 6.0, 1),
            "weather_level": classify(temperature, 0.0, 0.0, 0),
            "condition": "Simulated diurnal curve",
            "source": self.source,
        }

    def fetch(self, items: Sequence[Waypoint], context: FetchContext) -> dict[str, dict]:
        return {w.key: self.one(w, context.sim_minutes) for w in items}


PROVIDER = SimulatedWeatherProvider()
