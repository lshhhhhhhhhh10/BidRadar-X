from __future__ import annotations

from typing import Any

from ...intelligence.task_title import summarized_task_title
from ...schemas.tender import TenderNotice
from ...services.attachment_archive import AttachmentArchive
from .common import step


_PDF_CAPABLE_SOURCES = {"ccgp", "ggzy-national", "shanghai-ggzy", "cmcc-b2b"}


async def archive_tender_attachments(state: dict[str, Any]) -> dict[str, Any]:
    notices = [
        TenderNotice.model_validate(payload)
        for payload in state.get("relevant_documents", [])
    ]
    collection_name = summarized_task_title(
        state.get("task_spec"),
        fallback_query=state.get("query", ""),
    )
    eligible_indexes = [
        index
        for index, notice in enumerate(notices)
        if notice.source.source_id in _PDF_CAPABLE_SOURCES and notice.attachments
    ]
    eligible_notices = [notices[index] for index in eligible_indexes]
    archived_notices, archived, failed = await AttachmentArchive().archive_notices(
        eligible_notices,
        collection_name=collection_name,
    )
    updated = list(notices)
    for index, notice in zip(eligible_indexes, archived_notices, strict=True):
        updated[index] = notice
    return {
        "relevant_documents": [notice.model_dump(mode="json") for notice in updated],
        "funnel": {
            **state.get("funnel", {}),
            "archived_pdf": archived,
        },
        "steps": step(
            state,
            "招标文件本地归档",
            f"从相关公告附件中保存 {archived} 份 PDF 到本机；{failed} 份未能安全下载。",
            sum(len(notice.attachments) for notice in eligible_notices),
            archived,
            "completed" if failed == 0 else "warning",
        ),
    }
