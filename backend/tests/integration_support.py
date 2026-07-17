from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.schemas.tender import Attachment, SourceRecord, TenderNotice


def make_notice(
    *,
    source_id: str,
    source_name: str,
    source_url: str,
    marker: str,
    project_fingerprint: str = "3" * 64,
    attachment_url: str | None = None,
) -> TenderNotice:
    fetched_at = datetime.fromisoformat("2026-07-14T14:00:00+08:00")
    return TenderNotice(
        notice_id=f"{source_id}-{marker}",
        notice_type="tender",
        title="某单位服务器采购公告",
        published_at=datetime.fromisoformat("2026-07-14T09:00:00+08:00"),
        source=SourceRecord(
            source_id=source_id,
            source_name=source_name,
            source_url=source_url,
            publication_role="original",
            source_notice_id=marker,
            authority=1.0,
        ),
        core_content=f"采购服务器及配套服务，来源记录 {marker}。",
        attachments=(
            [
                Attachment(
                    attachment_id=f"attachment-{marker}",
                    name="采购需求附件.pdf",
                    url=attachment_url,
                    media_type="application/pdf",
                )
            ]
            if attachment_url
            else []
        ),
        raw_content_fingerprint=marker[0] * 64,
        notice_stable_fingerprint="2" * 64,
        project_stable_fingerprint=project_fingerprint,
        fetched_at=fetched_at,
    )


@dataclass
class SuccessfulSource:
    metadata: dict[str, Any]
    notices: list[TenderNotice]

    async def collect(self, task_spec: dict[str, Any], search_plan: dict[str, Any]):
        del task_spec, search_plan
        return self.notices


@dataclass
class FailingSource:
    metadata: dict[str, Any]
    message: str = "fixture source unavailable"

    async def collect(self, task_spec: dict[str, Any], search_plan: dict[str, Any]):
        del task_spec, search_plan
        raise RuntimeError(self.message)


def source_metadata(
    source_id: str,
    name: str,
    *,
    requires_login: bool = False,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "name": name,
        "authority": 1.0,
        "hit_rate": 0.8,
        "stability": 0.8,
        "cost": 0.2,
        "attempts": 0,
        "requires_login": requires_login,
    }


def isolated_source_set() -> list[Any]:
    return [
        SuccessfulSource(
            source_metadata("public-a", "公开来源 A"),
            [
                make_notice(
                    source_id="public-a",
                    source_name="公开来源 A",
                    source_url="https://public-a.gov.cn/notices/real-001",
                    marker="a",
                    attachment_url="https://public-a.gov.cn/notices/real-001/attachment.pdf",
                )
            ],
        ),
        SuccessfulSource(
            source_metadata("public-b", "公开来源 B"),
            [
                make_notice(
                    source_id="public-b",
                    source_name="公开来源 B",
                    source_url="https://public-b.gov.cn/notices/real-001",
                    marker="b",
                )
            ],
        ),
        FailingSource(
            source_metadata("login-source", "登录来源", requires_login=True),
            "authenticated fixture source is unavailable",
        ),
    ]
