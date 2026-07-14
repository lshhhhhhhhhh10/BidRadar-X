from __future__ import annotations

from typing import Any

from ...schemas.tender import TenderNotice
from .common import step


def judge_relevance(state: dict[str, Any]) -> dict[str, Any]:
    keywords = state["task_spec"]["keywords"]
    exclusions = state["task_spec"]["exclusions"]
    relevant: list[dict[str, Any]] = []
    for payload in state["normalized_documents"]:
        notice = TenderNotice.model_validate(payload)
        searchable = f"{notice.title} {notice.core_content}"
        matched = [keyword for keyword in keywords if keyword.casefold() in searchable.casefold()]
        excluded = [phrase for phrase in exclusions if phrase in searchable]
        if matched and not excluded:
            relevant.append(notice.model_dump(mode="json"))
    funnel = {**state["funnel"], "relevant": len(relevant)}
    return {
        "relevant_documents": relevant,
        "funnel": funnel,
        "steps": step(
            state,
            "相关性判断 Agent",
            "通过主题词与排除语境筛选契约化公告。",
            len(state["normalized_documents"]),
            len(relevant),
        ),
    }
