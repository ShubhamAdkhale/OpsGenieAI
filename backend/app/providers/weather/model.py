"""Weather domain rules, independent of where a reading came from.

Banding and delay live here rather than in either provider because BOTH
providers need them: a live Open-Meteo reading and a simulated diurnal one are
banded by the identical thresholds, which is the only reason a fallback reading
is safe to feed into the same risk engine. Keeping them next to one provider
would make the other one's banding a copy.
"""

from __future__ import annotations

from dataclasses import dataclass

# WMO weather interpretation codes -> our four bands.
THUNDERSTORM_CODES = {95, 96, 99}
RAIN_CODES = {61, 63, 65, 66, 67, 80, 81, 82}
DRIZZLE_CODES = {51, 53, 55, 56, 57, 45, 48}

# A heat event is a cold-chain event in its own right, independent of rain, so
# ambient temperature can push the band up on a cloudless day.
HEAT_EXTREME_C = 42.0
HEAT_STORM_C = 38.0

# Delay multipliers applied to a lane's base ETA.
WEATHER_DELAY_FACTOR = {"CLEAR": 0.0, "RAIN": 0.08, "STORM": 0.18, "EXTREME": 0.30}


@dataclass(frozen=True)
class Waypoint:
    city: str
    lat: float
    lon: float

    @property
    def key(self) -> str:
        """Identity for `ProviderChain`, which fans out and merges by key."""
        return self.city


def classify(temperature_c: float, precipitation_mm: float, wind_kph: float, code: int) -> str:
    """Band a reading. Transparent thresholds, not a model."""
    if temperature_c >= HEAT_EXTREME_C:
        return "EXTREME"
    if code in THUNDERSTORM_CODES:
        return "EXTREME" if (precipitation_mm >= 10.0 or wind_kph >= 60.0) else "STORM"
    if code in RAIN_CODES:
        return "STORM" if (precipitation_mm >= 7.5 or wind_kph >= 45.0) else "RAIN"
    if code in DRIZZLE_CODES:
        return "RAIN" if precipitation_mm >= 0.5 else "CLEAR"
    if temperature_c >= HEAT_STORM_C:
        return "STORM"
    if precipitation_mm >= 2.0 or wind_kph >= 50.0:
        return "RAIN"
    return "CLEAR"


def delay_factor(weather_level: str) -> float:
    return WEATHER_DELAY_FACTOR.get(weather_level, 0.0)
