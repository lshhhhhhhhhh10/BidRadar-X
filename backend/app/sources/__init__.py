"""Production source registry.

The legacy simulated adapters remain importable from their own modules for demo
fixtures, but they are intentionally absent from this registry.
"""

from __future__ import annotations

from .ccgp import CCGPSource
from .cmcc_b2b import CMCCB2BSource
from .ggzy import GGZYSource
from .tianyancha import TianyanchaSource


def build_production_sources() -> list[object]:
    """Build isolated adapter instances used by every production workflow run."""

    sources: list[object] = [
        CCGPSource(timeout=10, max_retries=1, min_interval=0.5),
        GGZYSource(timeout=10, retries=1, request_interval=0.25, max_pages=3),
        CMCCB2BSource(timeout=18),
    ]
    tianyancha = TianyanchaSource.from_environment(timeout=15)
    if tianyancha.configured:
        sources.append(tianyancha)
    return sources


__all__ = ["build_production_sources"]
