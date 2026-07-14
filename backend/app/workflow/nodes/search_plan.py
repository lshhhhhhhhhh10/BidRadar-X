from __future__ import annotations

from typing import Any

from .common import step


def plan_search(state: dict[str, Any]) -> dict[str, Any]:
    spec = state["task_spec"]
    region = " ".join(spec["regions"]) or "全国"
    queries = [f"{region} {keyword} 招标" for keyword in spec["keywords"][:4]]
    search_plan = {
        "queries": queries,
        "query": spec["topic"],
        "language": ["zh-CN"],
        "max_sources": 3,
        "max_pages": 1,
        "document_types": ["html", "dynamic_html", "pdf", "scan"],
    }
    return {
        "search_plan": search_plan,
        "steps": step(state, "检索规划 Agent", f"生成 {len(queries)} 组检索式。"),
    }
