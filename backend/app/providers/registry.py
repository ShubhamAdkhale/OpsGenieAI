"""The stream catalogue: every input and derivation, declared in one place.

`services/provenance.py` used to carry eight hand-written dicts describing what
the dashboard runs on. That list was correct only for as long as someone
remembered to edit it, and it had no connection to the code that actually
fetched anything - a stream could silently change source without its row
changing a word.

Here the declaration and the fetching are the same object. A stream that
ingests has a `ProviderChain`; a stream that derives has no chain and a fixed
`PREDICTED` label, because a formula's provenance is its inputs and it has no
source of its own. Adding traffic as a live feed later means adding a chain to
the row that already exists, and the UI updates itself.

Labels shown for INGESTED streams are DEFAULTS. What actually answered is only
known after a fetch, so a caller that has just fetched (or has stored rows to
inspect) passes the real label in as an override - see `rows()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from app.providers.base import PREDICTED, SIMULATED, Provider, ProviderChain
from app.providers.weather import open_meteo, simulated as simulated_weather

INGESTED = "INGESTED"
DERIVED = "DERIVED"


@dataclass(frozen=True)
class Stream:
    key: str
    name: str
    kind: str
    detail: str
    # Ordered live -> user -> simulated. Empty for a DERIVED stream, and also
    # for an INGESTED one that is still generated in-process (traffic, sensors,
    # demand) - those are the rows later phases replace rather than add to.
    providers: tuple[Provider, ...] = field(default_factory=tuple)
    default_label: str = SIMULATED

    @property
    def chain(self) -> ProviderChain | None:
        if not self.providers:
            return None
        return ProviderChain(self.key, self.providers)


# Order is the order the provenance panel renders: inputs first, then the
# things derived from them.
STREAMS: tuple[Stream, ...] = (
    Stream(
        key="weather",
        name="Weather",
        kind=INGESTED,
        detail="Open-Meteo where reachable, simulated diurnal curve otherwise.",
        providers=(open_meteo.PROVIDER, simulated_weather.PROVIDER),
    ),
    Stream(
        key="sensors",
        name="IoT sensors",
        kind=INGESTED,
        detail=(
            "Generated from a reefer wear model: temperature, vibration, current, "
            "pressure, humidity, cooling efficiency. No real telemetry."
        ),
    ),
    Stream(
        key="traffic",
        name="Traffic",
        kind=INGESTED,
        detail="Congestion from a rush-hour curve plus injected incidents.",
    ),
    Stream(
        key="demand",
        name="Demand history",
        kind=INGESTED,
        detail="90 days of synthetic daily demand per product.",
    ),
    Stream(
        key="cargo_temperature",
        name="Cargo temperature",
        kind=DERIVED,
        detail=(
            "Integrated from ambient weather, reefer cooling power and box "
            "conductance (Newton cooling)."
        ),
        default_label=PREDICTED,
    ),
    Stream(
        key="melt_index",
        name="Melt Index & spoilage",
        kind=DERIVED,
        detail="Transparent weighted formula, then a calibrated logistic curve.",
        default_label=PREDICTED,
    ),
    Stream(
        key="models",
        name="Demand forecast & failure risk",
        kind=DERIVED,
        detail="scikit-learn models.",
        default_label=PREDICTED,
    ),
    Stream(
        key="workflow",
        name="Workflow execution",
        kind=INGESTED,
        detail=(
            "Updates this application's own database. No courier, ERP or "
            "work-order system is called."
        ),
    ),
)

_BY_KEY = {stream.key: stream for stream in STREAMS}


def get(key: str) -> Stream:
    return _BY_KEY[key]


def chain(key: str) -> ProviderChain:
    """The fetch chain for an ingested stream.

    Raises rather than returning None: asking for the chain of a stream that
    has none is a programming error, and a silent None would surface much
    later as an empty result set.
    """
    resolved = _BY_KEY[key].chain
    if resolved is None:
        raise LookupError(f"Stream '{key}' has no provider chain (it is generated in-process).")
    return resolved


def rows(overrides: Mapping[str, tuple[str, str]] | None = None) -> list[dict]:
    """One row per stream for the provenance panel.

    `overrides` maps a stream key to the (label, detail) actually observed, for
    the streams whose answer is only knowable at runtime. Anything not
    overridden reports its declared default.
    """
    overrides = overrides or {}
    out: list[dict] = []
    for stream in STREAMS:
        label, detail = overrides.get(stream.key, (stream.default_label, stream.detail))
        out.append({"name": stream.name, "label": label, "detail": detail})
    return out
