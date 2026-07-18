"""Authenticated Tianyancha tender-search source.

The Tianyancha Open Platform exposes a documented HTTPS tender search API.
Users apply for interface 1063 and copy the resulting token from Data Center ->
My APIs.  BidRadar-X reads that token only on the server.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
from decimal import Decimal
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.schemas.tender import EvidenceReference, SourceRecord, TaskSpec, TenderNotice
from app.services.spend_guard import DailyBudgetExceededError, DailySpendGuard


TOKEN_ENV = "BIDRADAR_TIANYANCHA_TOKEN"
SEARCH_URL = "https://open.api.tianyancha.com/services/open/m/bids/search"
OPEN_PLATFORM_URL = "https://open.tianyancha.com/open/1063"
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
PER_CALL_COST_CNY = Decimal("0.20")


class TianyanchaSourceError(RuntimeError):
    """Base error for Tianyancha collection."""


class TianyanchaAuthenticationError(TianyanchaSourceError):
    """The server-side token is absent, expired, or lacks permission."""


class TianyanchaResponseError(TianyanchaSourceError):
    """Tianyancha returned an unusable response."""


@dataclass(frozen=True)
class TianyanchaHTTPResponse:
    url: str
    status_code: int
    payload: Mapping[str, Any]


class TianyanchaTransport(Protocol):
    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, str | int],
        headers: Mapping[str, str],
        timeout: float,
    ) -> TianyanchaHTTPResponse:
        ...


class _UrllibTransport:
    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, str | int],
        headers: Mapping[str, str],
        timeout: float,
    ) -> TianyanchaHTTPResponse:
        return await asyncio.to_thread(
            self._get_sync,
            url,
            params=params,
            headers=headers,
            timeout=timeout,
        )

    @staticmethod
    def _get_sync(
        url: str,
        *,
        params: Mapping[str, str | int],
        headers: Mapping[str, str],
        timeout: float,
    ) -> TianyanchaHTTPResponse:
        request_url = f"{url}?{urlencode(params)}"
        request = Request(request_url, headers=dict(headers), method="GET")
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise TianyanchaResponseError("Tianyancha response exceeded 10 MB")
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as error:
                raise TianyanchaResponseError(
                    "Tianyancha response was not valid JSON"
                ) from error
            if not isinstance(payload, Mapping):
                raise TianyanchaResponseError(
                    "Tianyancha response root was not an object"
                )
            return TianyanchaHTTPResponse(
                url=response.geturl(),
                status_code=response.status,
                payload=payload,
            )


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if cleaned:
            self.parts.append(cleaned)


class TianyanchaSource:
    """Collect tender notices through Tianyancha Open Platform API 1063."""

    metadata = {
        "source_id": "tianyancha-bids",
        "name": "天眼查开放平台 · 招投标搜索",
        "authority": 0.72,
        "hit_rate": 0.7,
        "stability": 0.9,
        "cost": 0.55,
        "attempts": 0,
        "requires_login": True,
        "credential_env": TOKEN_ENV,
        "authentication_mode": "open-platform-token",
    }

    def __init__(
        self,
        *,
        token: str | None = None,
        transport: TianyanchaTransport | None = None,
        timeout: float = 20.0,
        now: Callable[[], datetime] | None = None,
        spend_guard: DailySpendGuard | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._token = (token or "").strip()
        self._transport = transport or _UrllibTransport()
        self._timeout = timeout
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._spend_guard = spend_guard or DailySpendGuard()

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> TianyanchaSource:
        values = os.environ if environment is None else environment
        return cls(token=values.get(TOKEN_ENV), **kwargs)

    @property
    def configured(self) -> bool:
        return bool(self._token or os.environ.get(TOKEN_ENV, "").strip())

    async def collect(
        self,
        task_spec: TaskSpec | Mapping[str, Any],
        search_plan: Mapping[str, Any] | None = None,
    ) -> list[TenderNotice]:
        token = self._token or os.environ.get(TOKEN_ENV, "").strip()
        if not token:
            raise TianyanchaAuthenticationError(
                f"missing {TOKEN_ENV}; apply for API 1063 and copy its token"
            )

        task = (
            task_spec
            if isinstance(task_spec, TaskSpec)
            else TaskSpec.model_validate(dict(task_spec))
        )
        plan = dict(search_plan or {})
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now() must return a timezone-aware datetime")

        start = task.time_range_start or (now - timedelta(days=30))
        end = task.time_range_end or now
        params: dict[str, str | int] = {
            "keyword": str(plan.get("query") or task.topic).strip(),
            "publishStartTime": start.date().isoformat(),
            "publishEndTime": end.date().isoformat(),
            "searchType": "1,2,3",
            "pageNum": 1,
            "pageSize": min(max(int(plan.get("tianyancha_page_size", 20)), 1), 20),
        }
        if task.regions:
            params["province"] = task.regions[0].removesuffix("省").removesuffix("市")

        self._spend_guard.charge(
            provider="tianyancha-bids",
            amount=PER_CALL_COST_CNY,
            detail=f"招投标搜索：{params['keyword']}",
        )
        try:
            response = await self._transport.get(
                SEARCH_URL,
                params=params,
                headers={
                    "Accept": "application/json",
                    "Authorization": token,
                    "User-Agent": "BidRadar-X/0.1 (Tianyancha Open Platform client)",
                },
                timeout=self._timeout,
            )
        except (TianyanchaSourceError, DailyBudgetExceededError):
            raise
        except Exception as error:
            raise TianyanchaSourceError("Tianyancha request failed") from error

        if response.status_code in {401, 403}:
            raise TianyanchaAuthenticationError(
                "Tianyancha rejected the configured token"
            )
        if response.status_code != 200:
            raise TianyanchaResponseError(
                f"Tianyancha returned HTTP {response.status_code}"
            )

        error_code = _integer(response.payload.get("error_code"))
        if error_code in {300002, 300003, 300005, 300009, 300011}:
            raise TianyanchaAuthenticationError(
                f"Tianyancha authorization failed with error {error_code}"
            )
        if error_code not in {None, 0}:
            reason = _clean(response.payload.get("reason"))
            raise TianyanchaResponseError(
                f"Tianyancha API error {error_code}: {reason or 'unknown error'}"
            )

        result = response.payload.get("result")
        if not isinstance(result, Mapping):
            raise TianyanchaResponseError("Tianyancha response had no result object")
        records = result.get("items", [])
        if not isinstance(records, list):
            raise TianyanchaResponseError("Tianyancha result had no items list")

        fetched_at = now.astimezone(timezone.utc)
        notices: list[TenderNotice] = []
        for record in records:
            if not isinstance(record, Mapping):
                continue
            notice = self._to_notice(record, fetched_at=fetched_at)
            if notice is not None:
                notices.append(notice)
        return notices

    def _to_notice(
        self,
        record: Mapping[str, Any],
        *,
        fetched_at: datetime,
    ) -> TenderNotice | None:
        notice_id = _clean(record.get("uuid") or record.get("id"))
        title = _clean(record.get("title"))
        published_at = _parse_epoch_milliseconds(record.get("publishTime"))
        if not notice_id or not title or published_at is None:
            return None

        content = _html_to_text(_clean(record.get("content")))
        purchaser = _clean(record.get("purchaser")) or None
        notice_kind = _clean(record.get("type"))
        core_parts = [title]
        if content:
            core_parts.append(content)
        if purchaser:
            core_parts.append(f"采购人：{purchaser}")
        if notice_kind:
            core_parts.append(f"公告类型：{notice_kind}")
        core_content = "\n".join(core_parts)

        source_url = _https_url(record.get("bidUrl")) or OPEN_PLATFORM_URL
        canonical_url = _web_url(record.get("link"))
        raw_payload = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
        project_anchor = _clean(record.get("projectCode")) or title
        region = _clean(record.get("province")) or None
        evidence: list[EvidenceReference] = []
        if purchaser:
            evidence.append(
                EvidenceReference(
                    evidence_id=f"tyc-{notice_id}-purchaser",
                    field_path="purchaser",
                    source_url=source_url,
                    quote=f"采购人：{purchaser}",
                    fetched_at=fetched_at,
                )
            )
        if region:
            evidence.append(
                EvidenceReference(
                    evidence_id=f"tyc-{notice_id}-region",
                    field_path="region",
                    source_url=source_url,
                    quote=f"省份地区：{region}",
                    fetched_at=fetched_at,
                )
            )

        return TenderNotice(
            notice_id=f"tyc-{notice_id}",
            notice_type=_notice_type(notice_kind),
            title=title,
            published_at=published_at,
            source=SourceRecord(
                source_id=self.metadata["source_id"],
                source_name=self.metadata["name"],
                source_url=source_url,
                publication_role="republication",
                canonical_notice_url=canonical_url,
                source_notice_id=notice_id,
                authority=self.metadata["authority"],
            ),
            core_content=core_content,
            region=region,
            purchaser=purchaser,
            raw_content_fingerprint=_fingerprint(raw_payload),
            notice_stable_fingerprint=_fingerprint(
                notice_id, notice_kind, published_at.isoformat()
            ),
            project_stable_fingerprint=_fingerprint(project_anchor, purchaser or ""),
            fetched_at=fetched_at,
            evidence=evidence,
        )


def _parse_epoch_milliseconds(value: Any) -> datetime | None:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    if number > 10_000_000_000:
        number = number // 1000
    try:
        return datetime.fromtimestamp(number, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _notice_type(value: str) -> str:
    if any(word in value for word in ("中标", "成交", "结果")):
        return "award"
    if any(word in value for word in ("变更", "更正")):
        return "correction"
    if any(word in value for word in ("废标", "终止", "取消")):
        return "cancellation"
    if any(word in value for word in ("招标", "采购", "预告")):
        return "tender"
    return "other"


def _html_to_text(value: str) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    parser.feed(value[:2_000_000])
    parser.close()
    return " ".join(parser.parts)


def _https_url(value: Any) -> str | None:
    text = _clean(value)
    return text if text.startswith("https://") else None


def _web_url(value: Any) -> str | None:
    text = _clean(value)
    return text if text.startswith(("https://", "http://")) else None


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _fingerprint(*values: str) -> str:
    return sha256("|".join(values).encode("utf-8")).hexdigest()


__all__ = [
    "OPEN_PLATFORM_URL",
    "PER_CALL_COST_CNY",
    "SEARCH_URL",
    "TOKEN_ENV",
    "TianyanchaAuthenticationError",
    "TianyanchaHTTPResponse",
    "TianyanchaResponseError",
    "TianyanchaSource",
    "TianyanchaSourceError",
]
