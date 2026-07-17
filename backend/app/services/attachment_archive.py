"""Download public tender PDFs into a user-visible local archive."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
from typing import Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4
from zoneinfo import ZoneInfo

from pypdf import PdfReader

from ..schemas.tender import Attachment, TenderNotice


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
ATTACHMENT_DIR = Path(
    os.environ.get(
        "BIDRADAR_ATTACHMENT_DIR",
        str(Path.home() / "Documents" / "招投标公告"),
    )
).expanduser()
MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_TEXT = 200_000
MAX_PDF_PAGES = 160
MAX_ATTACHMENTS_PER_RUN = 30

_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_KNOWN_NON_PDF_SUFFIXES = {".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".7z"}


@dataclass(frozen=True)
class DownloadedPDF:
    content: bytes
    final_url: str
    media_type: str | None = None


PDFFetcher = Callable[[str], DownloadedPDF]


class _SourceHasNoPDFError(ValueError):
    pass


class _SourceAccessDeniedError(PermissionError):
    pass


class _PDFLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[str] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = urljoin(self.base_url, href)
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._href:
            return
        label = re.sub(r"\s+", " ", " ".join(self._parts)).strip()
        path = urlparse(self._href).path
        if re.search(r"\.pdf(?:$|[?#])", path, re.IGNORECASE) or re.search(
            r"PDF|附件|下载|招标文件|采购文件", label, re.IGNORECASE
        ):
            self.links.append(self._href)
        self._href = None
        self._parts = []


class AttachmentArchive:
    def __init__(
        self,
        *,
        root: Path | None = None,
        fetcher: PDFFetcher | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.root = (root or ATTACHMENT_DIR).expanduser()
        self._fetcher = fetcher or _fetch_public_pdf
        self._clock = clock or (lambda: datetime.now(SHANGHAI_TZ))

    async def archive_notices(
        self,
        notices: Sequence[TenderNotice],
        *,
        collection_name: str,
    ) -> tuple[list[TenderNotice], int, int]:
        """Archive candidate PDFs without making a failed file block the run."""

        directory = self.root / _safe_component(collection_name, fallback="未命名检索")
        semaphore = asyncio.Semaphore(3)
        scheduled = 0

        async def archive_one(attachment: Attachment) -> Attachment:
            nonlocal scheduled
            if scheduled >= MAX_ATTACHMENTS_PER_RUN:
                return attachment.model_copy(update={"archive_status": "failed"})
            scheduled += 1
            async with semaphore:
                return await asyncio.to_thread(
                    self._archive_attachment,
                    attachment,
                    directory,
                )

        tasks: list[tuple[int, int, asyncio.Task[Attachment]]] = []
        notice_attachments = [list(notice.attachments) for notice in notices]
        for notice_index, attachments in enumerate(notice_attachments):
            for attachment_index, attachment in enumerate(attachments):
                tasks.append(
                    (
                        notice_index,
                        attachment_index,
                        asyncio.create_task(archive_one(attachment)),
                    )
                )

        for notice_index, attachment_index, task in tasks:
            notice_attachments[notice_index][attachment_index] = await task

        updated = [
            notice.model_copy(update={"attachments": notice_attachments[index]})
            for index, notice in enumerate(notices)
        ]
        archived = sum(
            attachment.archive_status == "available"
            for notice in updated
            for attachment in notice.attachments
        )
        failed = sum(
            attachment.archive_status == "failed"
            for notice in updated
            for attachment in notice.attachments
        )
        return updated, archived, failed

    def _archive_attachment(self, attachment: Attachment, directory: Path) -> Attachment:
        if not _is_pdf_candidate(attachment):
            return attachment.model_copy(
                update={"archive_status": "unsupported", "archive_error": "not_pdf_response"}
            )

        target = directory / _attachment_filename(attachment)
        try:
            if target.is_file():
                content = target.read_bytes()
                if len(content) > MAX_PDF_BYTES or not content.startswith(b"%PDF-"):
                    raise ValueError("existing archive is not a valid PDF")
            else:
                attachment_url = str(attachment.url)
                downloaded = (
                    _fetch_cmcc_inline_pdf(attachment_url)
                    if _is_cmcc_notice_url(attachment_url)
                    else self._fetcher(attachment_url)
                )
                if downloaded.content.startswith(b"%PDF-"):
                    content = downloaded.content
                else:
                    resolved = self._resolve_pdf_landing_page(attachment, downloaded)
                    content = resolved.content
                if len(content) > MAX_PDF_BYTES:
                    raise ValueError("PDF exceeds size limit")
                if not content.startswith(b"%PDF-"):
                    raise ValueError("attachment response is not a PDF")
                directory.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(f".{target.name}.{uuid4().hex}.part")
                try:
                    with temporary.open("xb") as file:
                        file.write(content)
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)

            extracted_text = _extract_pdf_text(content)
            return attachment.model_copy(
                update={
                    "media_type": "application/pdf",
                    "content_sha256": sha256(content).hexdigest(),
                    "fetched_at": self._clock(),
                    "archive_status": "available",
                    "archive_error": None,
                    "local_path": str(target.resolve()),
                    "extracted_text": extracted_text,
                }
            )
        except _SourceHasNoPDFError:
            return attachment.model_copy(
                update={
                    "archive_status": "unsupported",
                    "archive_error": "source_has_no_pdf",
                    "local_path": None,
                    "extracted_text": None,
                }
            )
        except Exception as error:
            return attachment.model_copy(
                update={
                    "archive_status": "failed",
                    "archive_error": _archive_error_code(error),
                    "local_path": None,
                    "extracted_text": None,
                }
            )

    def _resolve_pdf_landing_page(
        self,
        attachment: Attachment,
        downloaded: DownloadedPDF,
    ) -> DownloadedPDF:
        landing_url = downloaded.final_url or str(attachment.url)
        candidates = _customs_pdf_candidates(landing_url, self._fetcher)
        if not candidates:
            try:
                html = downloaded.content.decode("utf-8-sig")
            except UnicodeDecodeError:
                try:
                    html = downloaded.content.decode("gb18030")
                except UnicodeDecodeError as error:
                    raise ValueError("attachment response is not a PDF") from error
            parser = _PDFLinkParser(landing_url)
            parser.feed(html)
            candidates = list(dict.fromkeys(parser.links))
            if not candidates and re.search(
                r"请先登录|登录后|验证码|无权访问|access denied|captcha|sign[ -]?in",
                html,
                flags=re.IGNORECASE,
            ):
                raise _SourceAccessDeniedError("source requires authentication")

        for candidate in candidates[:8]:
            fetched = self._fetcher(candidate)
            if fetched.content.startswith(b"%PDF-"):
                return fetched
        if candidates:
            raise ValueError("resolved attachment response is not a PDF")
        raise _SourceHasNoPDFError("source page exposes no downloadable PDF")


def _fetch_public_pdf(url: str) -> DownloadedPDF:
    _validate_public_http_url(url)
    request = Request(
        url,
        headers={
            "User-Agent": "BidRadar-X/1.1 (public tender attachment archive)",
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.1",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": _origin_referer(url),
        },
        method="GET",
    )
    with urlopen(request, timeout=18) as response:  # noqa: S310
        final_url = response.geturl()
        _validate_public_http_url(final_url)
        content = response.read(MAX_PDF_BYTES + 1)
        if len(content) > MAX_PDF_BYTES:
            raise ValueError("PDF exceeds size limit")
        return DownloadedPDF(
            content=content,
            final_url=final_url,
            media_type=response.headers.get_content_type(),
        )


def _is_cmcc_notice_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.hostname == "b2b.10086.cn" and parsed.fragment.startswith("/noticeDetail?")


def _fetch_cmcc_inline_pdf(url: str) -> DownloadedPDF:
    """Resolve the public China Mobile detail API's base64 PDF response."""

    parsed = urlparse(url)
    if not _is_cmcc_notice_url(url):
        raise ValueError("not a China Mobile notice URL")
    _, _, query = parsed.fragment.partition("?")
    values = parse_qs(query)
    payload = {
        "publishId": (values.get("publishId") or [""])[0],
        "publishUuid": (values.get("publishUuid") or [""])[0],
        "publishType": (values.get("publishType") or ["PROCUREMENT"])[0],
        "publishOneType": (values.get("publishOneType") or ["PROCUREMENT"])[0],
        "sfactApplColumn5": "PC",
    }
    if not payload["publishId"] or not payload["publishUuid"]:
        raise ValueError("China Mobile notice URL is missing identifiers")
    api_url = "https://b2b.10086.cn/api-b2b/api-sync-es/white_list_api/b2b/publish/queryDetail"
    request = Request(
        api_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "BidRadar-X/1.1 (public China Mobile attachment archive)",
        },
        method="POST",
    )
    context = ssl.create_default_context()
    context.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
    with urlopen(request, timeout=22, context=context) as response:  # noqa: S310
        body = response.read(MAX_PDF_BYTES * 2 + 1)
    try:
        response_payload = json.loads(body.decode("utf-8"))
        encoded = response_payload["data"]["noticeContent"]
        content_type = str(response_payload["data"].get("contentType") or "").lower()
        content = base64.b64decode(encoded, validate=True)
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("China Mobile detail response did not contain a valid PDF") from error
    if response_payload.get("code") != 0 or content_type != "pdf" or not content.startswith(b"%PDF-"):
        raise ValueError("China Mobile detail response was not a PDF")
    if len(content) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds size limit")
    return DownloadedPDF(content=content, final_url=url, media_type="application/pdf")


def _customs_pdf_candidates(url: str, fetcher: PDFFetcher) -> list[str]:
    parsed = urlparse(url)
    if not parsed.hostname or not parsed.hostname.endswith("customs.gov.cn"):
        return []
    article_ids = parse_qs(parsed.query).get("id", [])
    if not article_ids:
        return []
    article_id = article_ids[0]
    origin = f"{parsed.scheme}://{parsed.netloc}"
    api_url = (
        f"{origin}/purchase/portal/attachment/list?"
        f"{urlencode({'objectId': article_id})}"
    )
    response = fetcher(api_url)
    try:
        payload = json.loads(response.content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("attachment landing API returned invalid JSON") from error
    records = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError("attachment landing API changed structure")
    candidates: list[str] = []
    for record in records:
        if not isinstance(record, dict) or not record.get("fileName"):
            continue
        query = urlencode(
            {
                "path": str(record["fileName"]),
                "originName": str(record.get("originFileName") or "招标文件.pdf"),
                "objectId": article_id,
            }
        )
        candidates.append(f"{origin}/purchase/portal/attachment/download?{query}")
    return candidates


def _origin_referer(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}/"


def _archive_error_code(error: Exception) -> str:
    text = str(error).casefold()
    if isinstance(error, _SourceAccessDeniedError):
        return "access_denied"
    if isinstance(error, HTTPError) and error.code in {401, 403, 407, 429, 451}:
        return "access_denied"
    if isinstance(error, URLError):
        return "network_error"
    if "non-public" in text or "public http" in text:
        return "unsafe_url"
    if "size limit" in text:
        return "too_large"
    if "not a pdf" in text or "invalid pdf" in text:
        return "not_pdf_response"
    if isinstance(error, OSError):
        return "write_failed"
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "network_error"
    return "unknown"


def _validate_public_http_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("attachment URL must be public HTTP(S)")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    for answer in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM):
        address = ipaddress.ip_address(answer[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise ValueError("attachment URL resolved to a non-public address")


def _is_pdf_candidate(attachment: Attachment) -> bool:
    suffix = Path(urlparse(str(attachment.url)).path).suffix.casefold()
    name_suffix = Path(attachment.name or "").suffix.casefold()
    if suffix in _KNOWN_NON_PDF_SUFFIXES or name_suffix in _KNOWN_NON_PDF_SUFFIXES:
        return False
    return True


def _attachment_filename(attachment: Attachment) -> str:
    source_name = attachment.name or Path(urlparse(str(attachment.url)).path).name
    stem = Path(source_name).stem if source_name else "招标文件"
    safe_stem = _safe_component(stem, fallback="招标文件")[:70].rstrip(" ._")
    identity = re.sub(r"[^0-9a-zA-Z-]", "", attachment.attachment_id)[-12:] or "document"
    return f"{safe_stem}_{identity}.pdf"


def _safe_component(value: str, *, fallback: str) -> str:
    cleaned = _UNSAFE_FILENAME.sub("_", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._")
    return cleaned[:90].rstrip(" ._") or fallback


def _extract_pdf_text(content: bytes) -> str | None:
    try:
        reader = PdfReader(BytesIO(content), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                return None
        parts: list[str] = []
        length = 0
        for page in reader.pages[:MAX_PDF_PAGES]:
            text = (page.extract_text() or "").replace("\x00", " ").strip()
            if not text:
                continue
            remaining = MAX_EXTRACTED_TEXT - length
            if remaining <= 0:
                break
            parts.append(text[:remaining])
            length += min(len(text), remaining)
        result = "\n\n".join(parts).strip()
        return result or None
    except Exception:
        return None


__all__ = [
    "ATTACHMENT_DIR",
    "AttachmentArchive",
    "DownloadedPDF",
]
