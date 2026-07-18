from __future__ import annotations

import hashlib
from typing import Any

from ...schemas.tender import TenderNotice
from .common import step


def build_evidence(state: dict[str, Any]) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    for project in state["projects"]:
        for document in project["documents"]:
            notice = TenderNotice.model_validate(document["notice"])
            source_url = str(notice.source.source_url)
            digest = hashlib.sha1(f"{source_url}|{notice.core_content}".encode("utf-8")).hexdigest()[:12]
            evidence.append(
                {
                    "evidence_id": f"ev-{digest}",
                    "project_id": project["project_id"],
                    "source_id": notice.source.source_id,
                    "url": source_url,
                    "page_number": None,
                    "content": notice.core_content,
                    "authority": notice.source.authority or 0.5,
                }
            )
            for attachment in notice.attachments:
                if not attachment.extracted_text:
                    continue
                attachment_url = str(attachment.url)
                attachment_digest = hashlib.sha1(
                    f"{attachment_url}|{attachment.content_sha256 or ''}".encode("utf-8")
                ).hexdigest()[:12]
                evidence.append(
                    {
                        "evidence_id": f"ev-pdf-{attachment_digest}",
                        "project_id": project["project_id"],
                        "source_id": notice.source.source_id,
                        "url": attachment_url,
                        "attachment_id": attachment.attachment_id,
                        "document_name": attachment.name or "招标文件.pdf",
                        "page_number": None,
                        "content": attachment.extracted_text,
                        "authority": notice.source.authority or 0.5,
                    }
                )
    return {
        "evidence": evidence,
        "steps": step(state, "证据知识库", "将规范化内容切成带来源定位的项目级证据。", len(state["projects"]), len(evidence)),
    }
