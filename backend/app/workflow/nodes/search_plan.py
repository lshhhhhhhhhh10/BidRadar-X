from __future__ import annotations

from typing import Any

from ...ai.service import AICoordinator, append_audit
from .common import step


def plan_search(state: dict[str, Any]) -> dict[str, Any]:
    spec = state["task_spec"]
    region = " ".join(spec["regions"]) or "全国"
    expanded_phrases = state.get("query_expansion", {}).get("search_phrases", [])
    queries = list(
        dict.fromkeys(
            [
                *expanded_phrases,
                *[f"{region} {keyword} 招标" for keyword in spec["keywords"][:8]],
            ]
        )
    )[:12]
    fallback_plan = {
        "queries": queries,
        "query": spec["topic"],
        "search_terms": list(
            dict.fromkeys([spec["topic"], *spec["keywords"]])
        )[:6],
        "language": ["zh-CN"],
        "max_sources": 3,
        "max_pages": 1,
        "max_results_per_source": 20,
        "document_types": ["html", "dynamic_html", "pdf", "scan"],
    }
    from . import source_select

    available_sources = [
        {
            "source_id": adapter.metadata["source_id"],
            "name": adapter.metadata["name"],
            "requires_login": bool(adapter.metadata.get("requires_login")),
            "authority": adapter.metadata.get("authority", 0.5),
            "cost": adapter.metadata.get("cost", 0.5),
        }
        for adapter in source_select.SOURCE_ADAPTERS
    ]
    coordinator = AICoordinator()
    ai_plan, audit = coordinator.plan_search(
        {
            "task_spec": spec,
            "query_expansion": state.get("query_expansion", {}),
            "available_sources": available_sources,
            "rule_fallback": fallback_plan,
        }
    )
    known_source_ids = {item["source_id"] for item in available_sources}
    ai_used = ai_plan is not None
    search_plan = {
        **fallback_plan,
        **(
            {
                "queries": list(dict.fromkeys(ai_plan.queries))[:8],
                "recommended_source_ids": [
                    item for item in ai_plan.recommended_source_ids if item in known_source_ids
                ],
                "strategy_summary": ai_plan.strategy_summary,
                "planner": "ai",
            }
            if ai_plan is not None
            else {"recommended_source_ids": [], "planner": "rules"}
        ),
    }
    return {
        "search_plan": search_plan,
        "ai_audit": append_audit(state, audit),
        "steps": step(
            state,
            "检索规划 Agent",
            f"{'AI' if ai_used else '规则'}生成 {len(search_plan['queries'])} 组检索式；实际访问仍由固定来源适配器执行。",
        ),
    }
