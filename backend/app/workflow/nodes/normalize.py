from __future__ import annotations

from typing import Any

from ...schemas.tender import TenderNotice
from .common import step


def normalize_documents(state: dict[str, Any]) -> dict[str, Any]:
    notices = [
        TenderNotice.model_validate(document).model_dump(mode="json")
        for document in state["raw_documents"]
    ]
    funnel = {**state["funnel"], "normalized": len(notices)}
    return {
        "normalized_documents": notices,
        "funnel": funnel,
        "steps": step(
            state,
            "内容解析与标准化",
            "按统一 TenderNotice 契约重新校验真实来源输出。",
            len(state["raw_documents"]),
            len(notices),
        ),
    }
