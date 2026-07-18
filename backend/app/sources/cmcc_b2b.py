"""Public China Mobile procurement notices from the site's white-list API."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
import json
import re
import ssl
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pypdf import PdfReader

from app.schemas.tender import Attachment, EvidenceReference, SourceRecord, TaskSpec, TenderNotice


LIST_URL = "https://b2b.10086.cn/api-b2b/api-sync-es/white_list_api/b2b/publish/queryList"
DETAIL_URL = "https://b2b.10086.cn/api-b2b/api-sync-es/white_list_api/b2b/publish/queryDetail"
PORTAL_URL = "https://b2b.10086.cn/"
MAX_RESPONSE_BYTES = 55 * 1024 * 1024
MAX_PDF_TEXT = 160_000


class CMCCSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class CMCCHTTPResponse:
    url: str
    status_code: int
    payload: Mapping[str, Any]


class CMCCTransport(Protocol):
    async def post(self, url: str, *, payload: Mapping[str, Any], timeout: float) -> CMCCHTTPResponse:
        ...


class _UrllibTransport:
    async def post(self, url: str, *, payload: Mapping[str, Any], timeout: float) -> CMCCHTTPResponse:
        return await asyncio.to_thread(self._post_sync, url, payload=payload, timeout=timeout)

    @staticmethod
    def _post_sync(url: str, *, payload: Mapping[str, Any], timeout: float) -> CMCCHTTPResponse:
        body = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "BidRadar-X/1.1 (public China Mobile procurement client)",
            },
            method="POST",
        )
        with urlopen(request, timeout=timeout, context=_cmcc_ssl_context()) as response:  # noqa: S310
            content = response.read(MAX_RESPONSE_BYTES + 1)
            if len(content) > MAX_RESPONSE_BYTES:
                raise CMCCSourceError("China Mobile response exceeded size limit")
            try:
                payload_value = json.loads(content.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as error:
                raise CMCCSourceError("China Mobile response was not valid JSON") from error
            if not isinstance(payload_value, Mapping):
                raise CMCCSourceError("China Mobile response root was not an object")
            return CMCCHTTPResponse(response.geturl(), response.status, payload_value)


def _cmcc_ssl_context() -> ssl.SSLContext:
    """Keep certificate verification while allowing this legacy official host's handshake."""

    context = ssl.create_default_context()
    context.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
    return context


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"style", "script", "noscript"}:
            self.ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"style", "script", "noscript"} and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.ignored_depth:
            return
        cleaned = " ".join(data.split())
        if cleaned:
            self.parts.append(cleaned)


class CMCCB2BSource:
    metadata = {
        "source_id": "cmcc-b2b",
        "name": "中国移动采购与招标网",
        "authority": 0.91,
        "hit_rate": 0.78,
        "stability": 0.84,
        "cost": 0.08,
        "attempts": 0,
        "requires_login": False,
        "authentication_mode": "public-white-list-api",
    }

    def __init__(
        self,
        *,
        transport: CMCCTransport | None = None,
        timeout: float = 22.0,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._transport = transport or _UrllibTransport()
        self._timeout = timeout
        self._now = now or (lambda: datetime.now(timezone.utc))

    async def collect(
        self,
        task_spec: TaskSpec | Mapping[str, Any],
        search_plan: Mapping[str, Any] | None = None,
    ) -> list[TenderNotice]:
        task = task_spec if isinstance(task_spec, TaskSpec) else TaskSpec.model_validate(dict(task_spec))
        plan = dict(search_plan or {})
        now = self._now()
        start = task.time_range_start or (now - timedelta(days=90))
        end = task.time_range_end or now
        keyword = str(plan.get("query") or task.topic).strip()
        page_size = min(max(int(plan.get("cmcc_page_size", 10)), 1), 20)
        listing = await self._transport.post(
            LIST_URL,
            payload={
                "name": keyword,
                "publishType": "PROCUREMENT",
                "publishOneType": "PROCUREMENT",
                "purchaseType": "",
                "companyType": "",
                "size": page_size,
                "current": 1,
                "creationDateStart": start.date().isoformat(),
                "creationDateEnd": end.date().isoformat(),
                "sfactApplColumn5": "PC",
            },
            timeout=self._timeout,
        )
        records = _response_records(listing)
        semaphore = asyncio.Semaphore(4)

        async def build(record: Mapping[str, Any]) -> TenderNotice | None:
            async with semaphore:
                return await self._build_notice(record, fetched_at=now.astimezone(timezone.utc))

        notices = await asyncio.gather(*(build(record) for record in records[:page_size]))
        return [notice for notice in notices if notice is not None]

    async def _build_notice(
        self,
        record: Mapping[str, Any],
        *,
        fetched_at: datetime,
    ) -> TenderNotice | None:
        notice_id = _clean(record.get("id"))
        notice_uuid = _clean(record.get("uuid"))
        title = _clean(record.get("name"))
        if not notice_id or not notice_uuid or not title or _is_closed_notice(title):
            return None
        published_at = _parse_datetime(record.get("publishDate"))
        if published_at is None:
            return None
        params = {
            "publishId": notice_id,
            "publishUuid": notice_uuid,
            "publishType": _clean(record.get("publishType")) or "PROCUREMENT",
            "publishOneType": _clean(record.get("publishOneType")) or "PROCUREMENT",
        }
        detail_response = await self._transport.post(
            DETAIL_URL,
            payload={**params, "sfactApplColumn5": "PC"},
            timeout=self._timeout,
        )
        detail = _response_data(detail_response)
        content_type = _clean(detail.get("contentType")).lower()
        raw_content = str(detail.get("noticeContent") or "")
        if content_type == "pdf":
            core_content = _pdf_text(raw_content)
        else:
            core_content = _html_text(raw_content)
        project_name = _clean(detail.get("projectName"))
        if not core_content:
            core_content = project_name or title
        region = _clean(record.get("companyTypeName")) or None
        purchaser = _clean(detail.get("companyName")) or None
        deadline = _parse_datetime(detail.get("backDate") or record.get("backDate"))
        page_url = f"{PORTAL_URL}#/noticeDetail?{urlencode(params)}"
        attachments: list[Attachment] = []
        if content_type == "pdf" and raw_content:
            attachments.append(
                Attachment(
                    attachment_id=f"cmcc-{notice_id}-pdf",
                    name=f"{_safe_title(project_name or title)}.pdf",
                    url=page_url,
                    media_type="application/pdf",
                )
            )
        evidence: list[EvidenceReference] = []
        if region:
            evidence.append(_evidence(notice_id, "region", page_url, f"所属地区：{region}", fetched_at))
        if purchaser:
            evidence.append(_evidence(notice_id, "purchaser", page_url, f"采购人：{purchaser}", fetched_at))
        if deadline:
            evidence.append(_evidence(notice_id, "deadline", page_url, f"应答截止：{deadline.isoformat()}", fetched_at))
        fingerprint_source = json.dumps(dict(record), ensure_ascii=False, sort_keys=True, default=str)
        return TenderNotice(
            notice_id=f"cmcc-{notice_id}",
            notice_type="tender",
            title=title,
            published_at=published_at,
            source=SourceRecord(
                source_id=self.metadata["source_id"],
                source_name=self.metadata["name"],
                source_url=page_url,
                publication_role="original",
                canonical_notice_url=page_url,
                source_notice_id=notice_id,
                authority=self.metadata["authority"],
            ),
            core_content=core_content[:MAX_PDF_TEXT],
            attachments=attachments,
            region=region,
            purchaser=purchaser,
            deadline=deadline,
            raw_content_fingerprint=_fingerprint(fingerprint_source, core_content),
            notice_stable_fingerprint=_fingerprint(notice_id, notice_uuid, published_at.isoformat()),
            project_stable_fingerprint=_fingerprint(project_name or title, purchaser or ""),
            fetched_at=fetched_at,
            evidence=evidence,
        )


def _response_records(response: CMCCHTTPResponse) -> list[Mapping[str, Any]]:
    data = _response_data(response)
    content = data.get("content", [])
    if not isinstance(content, list):
        raise CMCCSourceError("China Mobile list response had no content list")
    return [item for item in content if isinstance(item, Mapping)]


def _response_data(response: CMCCHTTPResponse) -> Mapping[str, Any]:
    if response.status_code != 200:
        raise CMCCSourceError(f"China Mobile returned HTTP {response.status_code}")
    if response.payload.get("code") != 0:
        raise CMCCSourceError(_clean(response.payload.get("msg")) or "China Mobile API returned an error")
    data = response.payload.get("data")
    if not isinstance(data, Mapping):
        raise CMCCSourceError("China Mobile response had no data object")
    return data


def _pdf_text(value: str) -> str:
    try:
        content = base64.b64decode(value, validate=True)
        if not content.startswith(b"%PDF-") or len(content) > MAX_RESPONSE_BYTES:
            return ""
        reader = PdfReader(BytesIO(content))
        parts: list[str] = []
        for page in reader.pages[:120]:
            text = " ".join((page.extract_text() or "").split())
            if text:
                parts.append(text)
            if sum(len(item) for item in parts) >= MAX_PDF_TEXT:
                break
        return "\n".join(parts)[:MAX_PDF_TEXT]
    except Exception:
        return ""


def _html_text(value: str) -> str:
    parser = _HTMLText()
    parser.feed(value[:2_000_000])
    parser.close()
    return " ".join(parser.parts)[:MAX_PDF_TEXT]


def _parse_datetime(value: Any) -> datetime | None:
    text = _clean(value)
    if not text or text.startswith("1900-"):
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone(timedelta(hours=8))) if parsed.tzinfo is None else parsed


def _evidence(notice_id: str, field_path: str, url: str, quote: str, fetched_at: datetime) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=f"cmcc-{notice_id}-{field_path}",
        field_path=field_path,
        source_url=url,
        quote=quote,
        fetched_at=fetched_at,
    )


def _is_closed_notice(title: str) -> bool:
    return bool(re.search(r"中标|中选|成交|流标|废标|终止|失败公告|结果公示", title))


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_title(value: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" ._")[:100] or "中国移动采购公告"


def _fingerprint(*values: str) -> str:
    return sha256("|".join(values).encode("utf-8")).hexdigest()


__all__ = [
    "CMCCB2BSource",
    "CMCCHTTPResponse",
    "CMCCSourceError",
    "DETAIL_URL",
    "LIST_URL",
]
