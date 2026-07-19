"""Production source registry.

The legacy simulated adapters remain importable from their own modules for demo
fixtures, but they are intentionally absent from this registry.
"""

from __future__ import annotations

from .ccgp import CCGPSource
from .cmcc_b2b import CMCCB2BSource
from .ggzy import GGZYSource
from .sam_gov import SAMGovSource
from .tianyancha import TianyanchaSource


# A source may be shown as a planned catalog card without being callable.  This
# set is the single capability boundary used by the API and tests so the UI can
# never label an unregistered adapter as production-ready.
REGISTERED_SOURCE_IDS = frozenset(
    {"ccgp", "ggzy-national", "cmcc-b2b", "tianyancha-bids", "sam-gov"}
)


def build_production_sources() -> list[object]:
    """Build isolated adapter instances used by every production workflow run."""

    sources: list[object] = [
        CCGPSource(
            timeout=18,
            max_retries=3,
            min_interval=0.8,
            retry_backoff=1.0,
        ),
        GGZYSource(
            timeout=18,
            retries=3,
            request_interval=0.6,
            retry_backoff=1.0,
            max_pages=3,
        ),
        CMCCB2BSource(timeout=18),
    ]
    tianyancha = TianyanchaSource.from_environment(timeout=15)
    if tianyancha.configured:
        sources.append(tianyancha)
    sam_gov = SAMGovSource.from_environment(timeout=20)
    if sam_gov.configured:
        sources.append(sam_gov)
    return sources


__all__ = ["REGISTERED_SOURCE_IDS", "build_production_sources"]
