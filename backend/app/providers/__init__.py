"""Data ingestion boundary.

`base` defines what a provider is and how a chain falls back; `registry`
declares every stream the dashboard runs on and owns the chains. Services ask
the registry for a chain and never construct a provider themselves.
"""

from __future__ import annotations

from app.providers import base, registry
from app.providers.base import (
    LIVE,
    MIXED,
    PREDICTED,
    SIMULATED,
    USER,
    FetchContext,
    ProviderChain,
    label_for_source,
)

__all__ = [
    "base",
    "registry",
    "LIVE",
    "USER",
    "SIMULATED",
    "PREDICTED",
    "MIXED",
    "FetchContext",
    "ProviderChain",
    "label_for_source",
]
