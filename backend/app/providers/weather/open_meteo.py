"""Open-Meteo: the one genuinely live input in this build.

Keyless and public, which is why it is the feed that exists. One batched call
covers every waypoint: Open-Meteo accepts comma-separated coordinate lists and
answers in the same order, so fourteen lanes cost one request rather than
fourteen.
"""

from __future__ import annotations

import logging
from typing import Sequence

import httpx

from app.config import settings
from app.providers.base import LIVE_OPEN_METEO, FetchContext
from app.providers.weather.model import Waypoint, classify

log = logging.getLogger("opsgenie.providers.weather")

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


class OpenMeteoProvider:
    stream = "weather"
    source = LIVE_OPEN_METEO

    @property
    def enabled(self) -> bool:
        return bool(settings.weather_enabled)

    def fetch(self, items: Sequence[Waypoint], context: FetchContext) -> dict[str, dict]:
        """Returns {} on ANY failure - the chain falls through to the simulator.

        A waypoint whose entry comes back without a temperature is dropped
        rather than defaulted, so it falls through individually instead of
        contributing an invented reading under a LIVE label.
        """
        if not items:
            return {}
        params = {
            "latitude": ",".join(f"{w.lat:.4f}" for w in items),
            "longitude": ",".join(f"{w.lon:.4f}" for w in items),
            "current": (
                "temperature_2m,relative_humidity_2m,precipitation,"
                "wind_speed_10m,weather_code"
            ),
            "timezone": "auto",
        }
        try:
            response = httpx.get(
                OPEN_METEO_URL, params=params, timeout=settings.weather_timeout_seconds
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - the demo must survive this
            log.warning("Open-Meteo unavailable (%s); falling through.", exc)
            return {}

        # A single coordinate returns an object, several return a list.
        entries = payload if isinstance(payload, list) else [payload]
        out: dict[str, dict] = {}
        for waypoint, entry in zip(items, entries):
            current = (entry or {}).get("current") or {}
            temperature = current.get("temperature_2m")
            if temperature is None:
                continue
            precipitation = float(current.get("precipitation") or 0.0)
            wind_kph = float(current.get("wind_speed_10m") or 0.0)
            code = int(current.get("weather_code") or 0)
            out[waypoint.key] = {
                "temperature_c": round(float(temperature), 2),
                "humidity_pct": round(float(current.get("relative_humidity_2m") or 60.0), 1),
                "precipitation_mm": round(precipitation, 2),
                "wind_kph": round(wind_kph, 1),
                "weather_level": classify(float(temperature), precipitation, wind_kph, code),
                "condition": f"WMO code {code}",
                "source": self.source,
            }
        if out:
            log.info("Open-Meteo returned live weather for %d waypoint(s).", len(out))
        return out


PROVIDER = OpenMeteoProvider()
