"""The ingestion boundary: what a data source is, and how one is labelled.

Before this module existed, "where does this number come from" was decided
inline inside each service, and only weather had a real answer. That was
survivable while weather was the only external feed; it stops being survivable
the moment traffic, routing, demand and telemetry each need their own
live-else-fallback path, because the fallback logic gets copied four more times
and the provenance strip gets four more hand-maintained rows.

So a stream is now a NAMED CHAIN of providers, tried in order, and the label
the UI shows is derived from which one actually answered. The rules that made
the weather feed honest are hoisted here and apply to every stream:

  * a provider reports a FINE-GRAINED source string (`LIVE_OPEN_METEO`), which
    is what gets persisted, and the coarse label the UI shows (`LIVE`) is
    derived from it - never stored twice, never allowed to disagree;
  * a provider that raises, times out or returns nothing is skipped, not fatal;
  * fallback is PER ITEM, not per request, so twelve live waypoints and two
    simulated ones is a representable state rather than an all-or-nothing one.

`USER` is declared here but unused in this phase. It is the label for data the
operator owns - shipments, machines, demand history they imported - which is
what replaces the seeded universe later.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, Sequence, runtime_checkable

log = logging.getLogger("opsgenie.providers")


# ---------------------------------------------------------------------------
# Labels and sources
# ---------------------------------------------------------------------------

# The four coarse labels the UI is allowed to show. They are not decoration:
# a cold-chain dashboard that renders a simulated sensor trace and a real
# weather reading identically is making a claim it cannot support.
LIVE = "LIVE"
USER = "USER"
SIMULATED = "SIMULATED"
PREDICTED = "PREDICTED"
# Not a provider outcome - a summary verdict for a stream whose items did not
# all come from the same place, or whose values have been perturbed after the
# fact by a scenario injection.
MIXED = "MIXED"

VALID_LABELS = frozenset({LIVE, USER, SIMULATED, PREDICTED, MIXED})

# Fine-grained source strings. These are PERSISTED (WeatherObservation.source),
# so the values are fixed by existing rows and must not be renamed casually.
LIVE_OPEN_METEO = "LIVE_OPEN_METEO"
SIMULATED_FALLBACK = "SIMULATED_FALLBACK"
SIMULATED_INJECTED = "SIMULATED_INJECTED"


def label_for_source(source: str) -> str:
    """Coarse label for a persisted source string.

    Prefix-based rather than a lookup table, so a provider added later gets the
    right label without editing this function - the cost is that a new source
    string must start with `LIVE_`, `USER_` or `SIMULATED_`.
    """
    if source.startswith("LIVE_"):
        return LIVE
    if source.startswith("USER_"):
        return USER
    return SIMULATED


def combined_label(sources: Sequence[str]) -> str:
    """The stream-level verdict for a set of item sources.

    Unanimous or nothing: a stream is only LIVE when every item is, because
    "mostly live" rendered as LIVE is precisely the overclaim the labels exist
    to stop. An empty set is SIMULATED rather than LIVE for the same reason -
    the safe direction to err in is downwards.
    """
    labels = {label_for_source(s) for s in sources}
    if not labels:
        return SIMULATED
    if len(labels) == 1:
        return labels.pop()
    return MIXED


# ---------------------------------------------------------------------------
# The provider contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FetchContext:
    """Everything a provider may need that is not one of the items requested.

    `sim_minutes` is the simulated clock. Only the simulated providers read it,
    but it has to be on the context rather than passed around separately,
    because the chain cannot know which provider will end up answering.
    """

    sim_minutes: float = 0.0


@runtime_checkable
class Provider(Protocol):
    """One way of obtaining one stream.

    `fetch` returns `{item.key: values}` and is allowed to return FEWER keys
    than it was asked for - that is the normal way of saying "I have nothing
    for this one", and the chain moves those keys on to the next provider. It
    must not raise for an expected failure (network down, no key configured);
    the chain catches anyway, but a provider that leans on that loses the
    ability to say which items it partially answered.
    """

    stream: str
    source: str

    @property
    def enabled(self) -> bool:
        """False when switched off by config or missing a credential."""
        ...

    def fetch(self, items: Sequence[Any], context: FetchContext) -> dict[str, dict]:
        ...


class ProviderChain:
    """Ordered providers for one stream, with per-item fallback.

    The last provider in a chain must be one that cannot fail - a simulator -
    or the stream has states in which it returns nothing at all, and every
    consumer downstream then needs its own null handling. Chains are asserted
    to end in a provider whose source is not `LIVE_`.
    """

    def __init__(self, stream: str, providers: Sequence[Provider]) -> None:
        if not providers:
            raise ValueError(f"Stream '{stream}' needs at least one provider.")
        self.stream = stream
        self.providers = tuple(providers)

    def fetch(self, items: Sequence[Any], context: FetchContext) -> dict[str, dict]:
        """Try each provider in turn for whatever is still missing.

        Every returned value carries the `source` of the provider that produced
        it, so the caller never has to remember which one answered.
        """
        remaining = {item.key: item for item in items}
        out: dict[str, dict] = {}

        for provider in self.providers:
            if not remaining:
                break
            if not provider.enabled:
                continue
            try:
                answered = provider.fetch(list(remaining.values()), context)
            except Exception:  # noqa: BLE001 - a failing source degrades, never 500s
                log.exception(
                    "Provider %s/%s raised; falling through.", self.stream, provider.source
                )
                continue
            for key, values in answered.items():
                if key not in remaining:
                    continue
                values.setdefault("source", provider.source)
                out[key] = values
                remaining.pop(key, None)

        if remaining:
            # Only reachable if the terminal provider is disabled or buggy.
            log.error(
                "Stream '%s' produced nothing for %d item(s): %s",
                self.stream,
                len(remaining),
                ", ".join(sorted(remaining)),
            )
        return out
