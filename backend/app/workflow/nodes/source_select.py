from __future__ import annotations

from typing import Any

from ...intelligence.source_router import SourceRouter
from ...sources import build_production_sources
from .common import step


SOURCE_ADAPTERS = build_production_sources()


def _routing_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        **metadata,
        "authority": metadata.get("authority", 0.5),
        "hit_rate": metadata.get("hit_rate", 0.5),
        "stability": metadata.get("stability", 0.5),
        "cost": metadata.get("cost", 0.5),
        "attempts": metadata.get("attempts", 0),
    }


def select_sources(state: dict[str, Any]) -> dict[str, Any]:
    selected = SourceRouter().select(
        [_routing_metadata(adapter.metadata) for adapter in SOURCE_ADAPTERS],
        state["search_plan"]["max_sources"],
    )
    return {
        "selected_sources": selected,
        "steps": step(state, "成本感知来源路由", "选择真实公开来源和登录来源；登录来源授权状态将在采集阶段单独报告。", len(SOURCE_ADAPTERS), len(selected)),
    }
