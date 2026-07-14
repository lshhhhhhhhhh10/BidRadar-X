from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


AttachmentStatus = Literal[
    "discovered",
    "download_allowed",
    "downloaded",
    "blocked",
    "restricted",
    "invalid",
    "failed",
]


def _require_aware(value: datetime | None, field_name: str) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{field_name} must include a timezone")


@dataclass(frozen=True)
class StoredTask:
    task_id: str
    query: str
    frequency: str


@dataclass(frozen=True)
class StoredRun:
    run_id: str
    task_id: str
    status: str


@dataclass(frozen=True)
class AttachmentState:
    """Optional download state layered onto a discovered contract attachment."""

    status: AttachmentStatus = "discovered"
    media_type: str | None = None
    size_bytes: int | None = None
    content_sha256: str | None = None
    fetched_at: datetime | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")
        if self.content_sha256 is not None and (
            len(self.content_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.content_sha256)
        ):
            raise ValueError("content_sha256 must be a lowercase SHA-256 fingerprint")
        _require_aware(self.fetched_at, "fetched_at")
        if self.status == "downloaded" and (
            self.content_sha256 is None or self.fetched_at is None
        ):
            raise ValueError("downloaded attachments require content_sha256 and fetched_at")
        if self.failure_reason is not None and self.status not in {
            "blocked",
            "restricted",
            "invalid",
            "failed",
        }:
            raise ValueError("failure_reason requires a failure attachment status")


@dataclass(frozen=True)
class SourceResponseMetadata:
    """Limited, credential-free response metadata retained with a publication."""

    http_status: int | None = None
    content_type: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    metadata: dict[str, Any] | None = field(default=None)

    def __post_init__(self) -> None:
        sensitive_fragments = ("authorization", "cookie", "token", "api_key", "apikey")
        for key in self.metadata or {}:
            normalized = key.lower().replace("-", "_")
            if any(fragment in normalized for fragment in sensitive_fragments):
                raise ValueError("response metadata must not contain credentials")


@dataclass(frozen=True)
class SourceWatermark:
    """Recoverable source cursor using time plus a source-specific identity."""

    source_id: str
    published_at: datetime
    source_notice_id: str | None = None
    source_url: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.published_at, "published_at")
        if self.source_notice_id is None and self.source_url is None:
            raise ValueError("watermark requires source_notice_id or source_url")

    def to_cursor(self) -> WatermarkCursor:
        return WatermarkCursor(
            published_at=self.published_at,
            source_notice_id=self.source_notice_id,
            source_url=self.source_url,
        )


@dataclass(frozen=True)
class WatermarkCursor:
    """The time-plus-identity value persisted for one source watermark."""

    published_at: datetime
    source_notice_id: str | None = None
    source_url: str | None = None
    notice_stable_fingerprint: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.published_at, "published_at")
        if (
            self.source_notice_id is None
            and self.source_url is None
            and self.notice_stable_fingerprint is None
        ):
            raise ValueError("watermark cursor requires a recoverable source identity")
