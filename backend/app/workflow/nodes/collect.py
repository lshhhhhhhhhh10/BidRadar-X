from __future__ import annotations

import asyncio
from typing import Any

from ...schemas.tender import TenderNotice
from .common import step
from . import source_select


async def _collect_source(
    adapter: Any,
    task_spec: dict[str, Any],
    search_plan: dict[str, Any],
) -> tuple[dict[str, Any], list[TenderNotice]]:
    metadata = adapter.metadata
    try:
        raw_notices = await asyncio.wait_for(
            adapter.collect(task_spec, search_plan),
            timeout=90,
        )
        notices = [
            item if isinstance(item, TenderNotice) else TenderNotice.model_validate(item)
            for item in raw_notices
        ]
    except Exception as error:
        return (
            {
                "source_id": metadata["source_id"],
                "name": metadata["name"],
                "requires_login": bool(metadata.get("requires_login")),
                "status": "failed",
                "record_count": 0,
                "error_type": type(error).__name__,
                "error": str(error),
            },
            [],
        )
    return (
        {
            "source_id": metadata["source_id"],
            "name": metadata["name"],
            "requires_login": bool(metadata.get("requires_login")),
            "status": "success",
            "record_count": len(notices),
        },
        notices,
    )


async def collect_documents(state: dict[str, Any]) -> dict[str, Any]:
    selected_ids = {source["source_id"] for source in state["selected_sources"]}
    adapters = [
        adapter
        for adapter in source_select.SOURCE_ADAPTERS
        if adapter.metadata["source_id"] in selected_ids
    ]
    outcomes = await asyncio.gather(
        *(
            _collect_source(adapter, state["task_spec"], state["search_plan"])
            for adapter in adapters
        )
    )
    source_results = [result for result, _ in outcomes]
    results_by_id = {result["source_id"]: result for result in source_results}
    selected_sources = [
        {
            **source,
            "collection_status": results_by_id[source["source_id"]]["status"],
            "record_count": results_by_id[source["source_id"]]["record_count"],
            **(
                {
                    "error_type": results_by_id[source["source_id"]]["error_type"],
                    "error": results_by_id[source["source_id"]]["error"],
                }
                if results_by_id[source["source_id"]]["status"] == "failed"
                else {}
            ),
        }
        for source in state["selected_sources"]
    ]
    documents = [notice.model_dump(mode="json") for _, notices in outcomes for notice in notices]
    funnel = {**state.get("funnel", {}), "raw": len(documents)}
    succeeded = sum(result["status"] == "success" for result in source_results)
    failed = len(source_results) - succeeded
    return {
        "status": "failed" if not adapters or succeeded == 0 else state.get("status", "running"),
        "raw_documents": documents,
        "selected_sources": selected_sources,
        "funnel": funnel,
        "steps": step(state, "多源采集 Agent 集群", f"{succeeded} 个来源成功、{failed} 个来源失败，获得 {len(documents)} 条真实候选。", len(adapters), len(documents), "completed" if succeeded else "failed"),
    }
