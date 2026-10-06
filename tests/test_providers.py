"""The ingestion boundary.

These cover the properties every later feed will depend on, using fake
providers rather than the weather ones, so they keep testing the CHAIN when
traffic, routing and telemetry are added to it.

The two that matter most:

* fallback is PER ITEM, not per request - a partial live answer must keep the
  rows it got rather than discarding them for consistency with the ones it
  missed, or a single bad coordinate downgrades the whole feed;
* the coarse label is DERIVED from the persisted source, so a simulated
  reading has no path to wearing a LIVE chip.
"""

from __future__ import annotations

import pytest

from app.providers import registry
from app.providers.base import (
    LIVE,
    MIXED,
    PREDICTED,
    SIMULATED,
    USER,
    VALID_LABELS,
    FetchContext,
    ProviderChain,
    combined_label,
    label_for_source,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Item:
    def __init__(self, key: str) -> None:
        self.key = key


class _Fake:
    """A provider that answers for exactly the keys it was told to."""

    stream = "test"

    def __init__(self, source: str, answers: set[str], enabled: bool = True) -> None:
        self.source = source
        self._answers = answers
        self._enabled = enabled
        self.calls: list[list[str]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    def fetch(self, items, context):
        self.calls.append([i.key for i in items])
        return {i.key: {"value": i.key} for i in items if i.key in self._answers}


class _Exploding:
    stream = "test"
    source = "LIVE_EXPLODES"
    enabled = True

    def fetch(self, items, context):
        raise OSError("no network")


def _items(*keys: str) -> list[_Item]:
    return [_Item(k) for k in keys]


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source,expected",
    [
        ("LIVE_OPEN_METEO", LIVE),
        ("LIVE_TOMTOM_INCIDENTS", LIVE),
        ("USER_CSV_IMPORT", USER),
        ("SIMULATED_FALLBACK", SIMULATED),
        ("SIMULATED_INJECTED", SIMULATED),
        # Anything unrecognised is simulated. Erring the other way would let a
        # typo in a source string promote made-up data to LIVE.
        ("something_unlabelled", SIMULATED),
    ],
)
def test_label_is_derived_from_the_source_prefix(source, expected):
    assert label_for_source(source) == expected


@pytest.mark.parametrize(
    "sources,expected",
    [
        (["LIVE_A", "LIVE_B"], LIVE),
        (["SIMULATED_FALLBACK", "SIMULATED_INJECTED"], SIMULATED),
        # Unanimous or nothing. "Mostly live" shown as LIVE is the overclaim
        # the labels exist to stop.
        (["LIVE_A", "SIMULATED_FALLBACK"], MIXED),
        (["USER_CSV", "LIVE_A"], MIXED),
        # Nothing observed errs downwards, never towards LIVE.
        ([], SIMULATED),
    ],
)
def test_a_stream_is_only_live_when_every_item_is(sources, expected):
    assert combined_label(sources) == expected


# ---------------------------------------------------------------------------
# Chain behaviour
# ---------------------------------------------------------------------------


def test_first_provider_that_answers_wins():
    live = _Fake("LIVE_X", {"a", "b"})
    sim = _Fake("SIMULATED_X", {"a", "b"})
    result = ProviderChain("test", [live, sim]).fetch(_items("a", "b"), FetchContext())

    assert {k: v["source"] for k, v in result.items()} == {"a": "LIVE_X", "b": "LIVE_X"}
    # The fallback is never asked about keys that were already answered.
    assert sim.calls == []


def test_fallback_is_per_item_not_per_request():
    """A partial live answer keeps its live rows and tops up the rest."""
    live = _Fake("LIVE_X", {"a", "c"})
    sim = _Fake("SIMULATED_X", {"a", "b", "c", "d"})
    result = ProviderChain("test", [live, sim]).fetch(_items("a", "b", "c", "d"), FetchContext())

    assert {k: v["source"] for k, v in result.items()} == {
        "a": "LIVE_X",
        "b": "SIMULATED_X",
        "c": "LIVE_X",
        "d": "SIMULATED_X",
    }
    # The simulator was asked ONLY for what was still missing.
    assert sorted(sim.calls[0]) == ["b", "d"]


def test_a_disabled_provider_is_skipped_entirely():
    live = _Fake("LIVE_X", {"a"}, enabled=False)
    sim = _Fake("SIMULATED_X", {"a"})
    result = ProviderChain("test", [live, sim]).fetch(_items("a"), FetchContext())

    assert result["a"]["source"] == "SIMULATED_X"
    assert live.calls == []


def test_a_raising_provider_degrades_instead_of_propagating():
    """A failing source must never reach the caller as an exception.

    This is the property that keeps a dead API from turning the dashboard into
    a 500 - the demo has to survive it, and say that it did.
    """
    sim = _Fake("SIMULATED_X", {"a", "b"})
    result = ProviderChain("test", [_Exploding(), sim]).fetch(_items("a", "b"), FetchContext())

    assert set(result) == {"a", "b"}
    assert all(v["source"] == "SIMULATED_X" for v in result.values())


def test_a_provider_may_not_overwrite_an_answer_it_was_not_asked_for():
    """A chatty provider returning extra keys cannot inject unrequested items."""
    live = _Fake("LIVE_X", {"a", "zzz"})
    sim = _Fake("SIMULATED_X", {"a"})
    result = ProviderChain("test", [live, sim]).fetch(_items("a"), FetchContext())

    assert set(result) == {"a"}


def test_a_provider_keeps_a_source_it_set_itself():
    """Injected readings carry their own source, not the provider's default."""

    class _Injecting:
        stream = "test"
        source = "LIVE_X"
        enabled = True

        def fetch(self, items, context):
            return {i.key: {"source": "SIMULATED_INJECTED"} for i in items}

    result = ProviderChain("test", [_Injecting()]).fetch(_items("a"), FetchContext())
    assert result["a"]["source"] == "SIMULATED_INJECTED"


def test_a_chain_needs_at_least_one_provider():
    with pytest.raises(ValueError):
        ProviderChain("test", [])


def test_context_reaches_the_provider():
    seen = {}

    class _Reader:
        stream = "test"
        source = "SIMULATED_X"
        enabled = True

        def fetch(self, items, context):
            seen["sim_minutes"] = context.sim_minutes
            return {i.key: {} for i in items}

    ProviderChain("test", [_Reader()]).fetch(_items("a"), FetchContext(sim_minutes=930.0))
    assert seen["sim_minutes"] == 930.0


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_every_declared_stream_is_well_formed():
    assert registry.STREAMS
    for stream in registry.STREAMS:
        assert stream.default_label in VALID_LABELS
        assert stream.detail
        assert stream.kind in {registry.INGESTED, registry.DERIVED}
        # A derived stream has no source of its own - its provenance is its
        # inputs - so it must never carry a chain.
        if stream.kind == registry.DERIVED:
            assert stream.providers == ()
            assert stream.default_label == PREDICTED


def test_weather_is_the_only_stream_with_a_live_chain_so_far():
    with_chains = {s.key for s in registry.STREAMS if s.providers}
    assert with_chains == {"weather"}


def test_a_chain_ends_in_a_provider_that_cannot_fail():
    """The terminal provider must be a simulator, or the stream can return
    nothing at all and every consumer downstream needs its own null handling."""
    for stream in registry.STREAMS:
        if not stream.providers:
            continue
        terminal = stream.providers[-1]
        assert terminal.enabled is True
        assert label_for_source(terminal.source) == SIMULATED


def test_asking_for_a_chain_that_does_not_exist_is_loud():
    """Traffic gets a chain in a later phase; until then this must not
    silently return an empty result set."""
    with pytest.raises(LookupError):
        registry.chain("traffic")


def test_rows_report_declared_defaults_and_accept_overrides():
    default_rows = {r["name"]: r for r in registry.rows()}
    assert default_rows["Weather"]["label"] == SIMULATED

    overridden = {
        r["name"]: r for r in registry.rows(overrides={"weather": (LIVE, "14/14 live")})
    }
    assert overridden["Weather"]["label"] == LIVE
    assert overridden["Weather"]["detail"] == "14/14 live"
    # An override touches only its own row.
    assert overridden["IoT sensors"] == default_rows["IoT sensors"]


def test_row_order_is_the_declared_order():
    assert [r["name"] for r in registry.rows()] == [s.name for s in registry.STREAMS]
