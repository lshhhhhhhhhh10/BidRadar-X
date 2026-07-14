"""Production source registry.

The legacy simulated adapters remain importable from their own modules for demo
fixtures, but they are intentionally absent from this registry.
"""

from __future__ import annotations

from .ccgp import CCGPSource
from .ggzy import GGZYSource
from .jianyu import JianyuSource


def build_production_sources() -> list[object]:
    """Build isolated adapter instances used by every production workflow run."""

    return [
        CCGPSource(timeout=10, max_retries=1, min_interval=0.5),
        GGZYSource(timeout=10, retries=1, request_interval=0.25, max_pages=3),
        JianyuSource(),
    ]


__all__ = ["build_production_sources"]
