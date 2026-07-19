"""China Government Procurement Network (CCGP) public notice adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
from html.parser import HTMLParser
import logging
import mimetypes
import re
from threading import Lock
from time import monotonic
from typing import Any, Awaitable, Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from app.schemas.tender import (
    Attachment,
    EvidenceReference,
    SourceRecord,
    TaskSpec,
    TenderNotice,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_SPACE_RE = re.compile(r"\s+")
_MAX_HTML_BYTES = 10_000_000
_DATE_PATTERNS = (
    "%Y-%m-%d %H:%M",
    "%Y.%m.%d %H:%M",
    "%Y年%m月%d日 %H:%M",
    "%Y-%m-%d",
    "%Y.%m.%d",
    "%Y年%m月%d日",
)
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
logger = logging.getLogger(__name__)


class CCGPError(RuntimeError):
    """Base error for an unsuccessful CCGP collection operation."""


class CCGPParseError(CCGPError):
    """Raised when a required source fact cannot be parsed."""


class CCGPAccessBlockedError(CCGPError):
    """Raised when CCGP asks the caller to stop or complete a security check."""


class CCGPTemporaryUnavailableError(CCGPError):
    """Raised when CCGP's public search service stays busy after retries."""


@dataclass(frozen=True)
class HTTPResponse:
    url: str
    text: str
    status_code: int = 200
    content: bytes | None = None


class HTTPTransport(Protocol):
    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str],
        timeout: float,
    ) -> HTTPResponse:
        ...


class _UrllibTransport:
    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str],
        timeout: float,
    ) -> HTTPResponse:
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
        params: dict[str, Any] | None,
        headers: dict[str, str],
        timeout: float,
    ) -> HTTPResponse:
        request_url = f"{url}?{urlencode(params)}" if params else url
        request = Request(request_url, headers=headers, method="GET")
        # The adapter validates all requested and redirected hosts as CCGP domains.
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read(_MAX_HTML_BYTES + 1)
            if len(body) > _MAX_HTML_BYTES:
                raise CCGPError("CCGP response exceeded the 10 MB HTML limit")
            charset = response.headers.get_content_charset() or "utf-8"
            return HTTPResponse(
                url=response.geturl(),
                text=body.decode(charset, errors="replace"),
                status_code=response.status,
                content=body,
            )


@dataclass(frozen=True)
class _SearchItem:
    url: str
    title: str
    published_at: datetime | None
    region: str | None


@dataclass(frozen=True)
class _AttachmentLink:
    url: str
    name: str | None


class _ChannelListParser(HTMLParser):
    """Parse CCGP's official central/local announcement directory pages."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.items: list[_SearchItem] = []
        self.found_listing = False
        self._item_depth = 0
        self._href: str | None = None
        self._title = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "li" and self._item_depth == 0:
            self._item_depth = 1
            self._href = None
            self._title = ""
            self._text = []
            return
        if not self._item_depth:
            return
        if tag not in _VOID_TAGS:
            self._item_depth += 1
        if tag == "a" and attributes.get("href"):
            candidate = urljoin(self.base_url, attributes["href"] or "")
            if _is_ccgp_url(candidate):
                self._href = candidate
                self._title = _clean_text(attributes.get("title") or "")

    def handle_endtag(self, tag: str) -> None:
        if not self._item_depth:
            return
        if tag == "li" and self._item_depth == 1:
            self._finish_item()
            self._item_depth = 0
        elif self._item_depth > 1:
            self._item_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._item_depth:
            self._text.append(data)

    def _finish_item(self) -> None:
        text = _clean_text(" ".join(self._text))
        title = self._title or _clean_text(text.split("发布时间", 1)[0])
        if not self._href or not title or _find_datetime(text) is None:
            return
        self.found_listing = True
        self.items.append(
            _SearchItem(
                url=self._href,
                title=title,
                published_at=_find_datetime(text),
                region=_find_list_region(text),
            )
        )


class _SearchResultParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.items: list[_SearchItem] = []
        self.found_results_container = False
        self._in_results = 0
        self._in_item = 0
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self._in_anchor = False
        self._item_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "ul" and "vT-srch-result-list-bid" in classes:
            self.found_results_container = True
            self._in_results = 1
            return
        if self._in_results:
            if tag not in _VOID_TAGS:
                self._in_results += 1
            if tag == "li" and not self._in_item:
                self._in_item = 1
                self._anchor_href = None
                self._anchor_text = []
                self._item_text = []
            elif self._in_item and tag not in _VOID_TAGS:
                self._in_item += 1
            if self._in_item and tag == "a" and attributes.get("href"):
                self._anchor_href = urljoin(self.base_url, attributes["href"] or "")
                self._in_anchor = True

    def handle_endtag(self, tag: str) -> None:
        if self._in_item:
            if tag == "a":
                self._in_anchor = False
            if tag == "li" and self._in_item == 1:
                self._finish_item()
                self._in_item = 0
            elif self._in_item > 1:
                self._in_item -= 1
        if self._in_results:
            if tag == "ul" and self._in_results == 1:
                self._in_results = 0
            elif self._in_results > 1:
                self._in_results -= 1

    def handle_data(self, data: str) -> None:
        if not self._in_item:
            return
        self._item_text.append(data)
        if self._in_anchor:
            self._anchor_text.append(data)

    def _finish_item(self) -> None:
        title = _clean_text(" ".join(self._anchor_text))
        if not self._anchor_href or not title or not _is_ccgp_url(self._anchor_href):
            return
        item_text = _clean_text(" ".join(self._item_text))
        self.items.append(
            _SearchItem(
                url=self._anchor_href,
                title=title,
                published_at=_find_datetime(item_text),
                region=_find_list_region(item_text),
            )
        )


class _DetailParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.meta: dict[str, str] = {}
        self.table_fields: dict[str, str] = {}
        self.content_parts: list[str] = []
        self.attachments: list[_AttachmentLink] = []
        self._content_depth = 0
        self._skip_depth = 0
        self._in_row = False
        self._row_cells: list[tuple[bool, str]] = []
        self._cell_is_label = False
        self._cell_parts: list[str] | None = None
        self._anchor_href: str | None = None
        self._anchor_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "meta":
            name = attributes.get("name")
            content = attributes.get("content")
            if name and content:
                self.meta[name] = content

        if tag == "tr":
            self._in_row = True
            self._row_cells = []
        elif self._in_row and tag in {"td", "th"}:
            self._cell_is_label = "title" in classes
            self._cell_parts = []

        if tag == "div" and "vF_detail_content" in classes and not self._content_depth:
            self._content_depth = 1
        elif self._content_depth and tag not in _VOID_TAGS:
            self._content_depth += 1

        if self._content_depth:
            if tag in {"script", "style"}:
                self._skip_depth += 1
            if tag in {"br", "p", "div", "h1", "h2", "h3", "h4", "h5", "li", "tr"}:
                self.content_parts.append("\n")
            href = attributes.get("href") if tag == "a" else None
            if href:
                candidate = urljoin(self.base_url, href)
                if _is_http_url(candidate):
                    self._anchor_href = candidate
                    self._anchor_parts = []
            gm_download = attributes.get("gm-download")
            if gm_download and _is_http_url(gm_download):
                self.attachments.append(
                    _AttachmentLink(
                        url=gm_download,
                        name=_clean_text(attributes.get("list-name") or "") or None,
                    )
                )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._cell_parts is not None and tag in {"td", "th"}:
            self._row_cells.append(
                (self._cell_is_label, _clean_text(" ".join(self._cell_parts)))
            )
            self._cell_parts = None
        if tag == "tr" and self._in_row:
            self._finish_row()
            self._in_row = False

        if self._content_depth:
            if tag == "a" and self._anchor_href:
                name = _clean_text(" ".join(self._anchor_parts)) or None
                if _looks_like_attachment(self._anchor_href, name):
                    self.attachments.append(_AttachmentLink(self._anchor_href, name))
                self._anchor_href = None
                self._anchor_parts = []
            if tag in {"script", "style"} and self._skip_depth:
                self._skip_depth -= 1
            self._content_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)
        if self._content_depth and not self._skip_depth:
            self.content_parts.append(data)
            if self._anchor_href:
                self._anchor_parts.append(data)

    def _finish_row(self) -> None:
        for index, (is_label, label) in enumerate(self._row_cells):
            if not is_label or not label:
                continue
            for _, value in self._row_cells[index + 1 :]:
                if value:
                    self.table_fields.setdefault(label.rstrip("：:"), value)
                    break


class CCGPSource:
    """Collect public procurement notices from the official CCGP website."""

    SEARCH_URL = "https://search.ccgp.gov.cn/bxsearch"
    FALLBACK_CHANNEL_URLS = (
        "https://www.ccgp.gov.cn/cggg/zygg/gkzb/",
        "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/",
    )
    USER_AGENT = "BidRadar-X/0.1 (compatible; public procurement notice collector)"
    metadata = {
        "source_id": "ccgp",
        "name": "中国政府采购网",
        "authority": 1.0,
        "hit_rate": 0.8,
        "stability": 0.75,
        "cost": 0.2,
        "attempts": 0,
        "requires_login": False,
    }

    def __init__(
        self,
        *,
        transport: HTTPTransport | None = None,
        timeout: float = 15.0,
        max_retries: int = 2,
        min_interval: float = 1.0,
        retry_backoff: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = monotonic,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if min_interval < 0:
            raise ValueError("min_interval must not be negative")
        if retry_backoff < 0:
            raise ValueError("retry_backoff must not be negative")
        self._transport = transport or _UrllibTransport()
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self.retry_backoff = retry_backoff
        self._sleep = sleep
        self._clock = clock
        self._now = now or (lambda: datetime.now(tz=SHANGHAI_TZ))
        # A production adapter is shared by scheduled and interactive runs, which
        # may execute on different asyncio event loops. A regular lock protects
        # rate-limit slot reservation without ever being awaited across loops.
        self._rate_limit_lock = Lock()
        self._last_request_started: float | None = None

    async def collect(
        self,
        task_spec: TaskSpec | Mapping[str, Any],
        search_plan: Mapping[str, Any],
    ) -> list[TenderNotice]:
        task = (
            task_spec
            if isinstance(task_spec, TaskSpec)
            else TaskSpec.model_validate(dict(task_spec))
        )
        max_pages = min(max(int(search_plan.get("max_pages", 1)), 1), 20)
        max_notices = min(
            max(int(search_plan.get("max_results_per_source", 20)), 1),
            50,
        )
        notices: list[TenderNotice] = []
        seen_urls: set[str] = set()
        planned_terms = [
            str(value).strip()
            for value in search_plan.get("search_terms", [])
            if str(value).strip()
        ][:6]
        search_terms: list[str | None] = planned_terms or [None]

        query_regions = task.regions or [""]
        successful_search_requests = 0
        last_search_error: Exception | None = None
        search_blocked = False
        for query_region in query_regions:
            region_scope = [query_region] if query_region else []
            for search_term in search_terms:
                for page_index in range(1, max_pages + 1):
                    try:
                        response = await self._request(
                            self.SEARCH_URL,
                            params=self._search_params(
                                task,
                                page_index,
                                query_region,
                                search_term=search_term,
                            ),
                        )
                        _raise_if_access_blocked(response)
                        parser = _SearchResultParser(response.url)
                        parser.feed(response.text)
                        if not parser.found_results_container:
                            raise CCGPParseError(
                                "CCGP search page did not contain the expected results list"
                            )
                    except CCGPAccessBlockedError as error:
                        last_search_error = error
                        search_blocked = True
                        break
                    except CCGPError as error:
                        last_search_error = error
                        break
                    successful_search_requests += 1
                    if not parser.items:
                        break
                    for item in parser.items:
                        if (
                            item.url in seen_urls
                            or not _within_time_range(item.published_at, task)
                            or not _region_matches(item.region, region_scope)
                        ):
                            continue
                        seen_urls.add(item.url)
                        try:
                            detail_response = await self._request(item.url, params=None)
                            _raise_if_access_blocked(detail_response)
                            notice = self._parse_notice(detail_response, task)
                        except CCGPError as error:
                            logger.warning(
                                "Skipping unavailable CCGP detail %s: %s",
                                item.url,
                                error,
                            )
                            continue
                        if not _within_time_range(notice.published_at, task):
                            continue
                        if not _region_matches(notice.region, region_scope):
                            continue
                        if _matches_exclusion(notice, task.exclusions):
                            continue
                        notices.append(notice)
                        if len(notices) >= max_notices:
                            return notices
                if search_blocked:
                    break
            if search_blocked:
                break

        # The public search service occasionally serves a stop/busy page while
        # CCGP's official announcement directories remain available. Falling
        # back to those same-domain directories turns that transient condition
        # into a valid (possibly empty) source result without bypassing controls.
        if successful_search_requests == 0:
            if isinstance(last_search_error, CCGPParseError):
                raise last_search_error
            fallback_succeeded = False
            fallback_error: Exception | None = None
            for channel_url in self.FALLBACK_CHANNEL_URLS:
                for page_index in range(max_pages):
                    page_url = _channel_page_url(channel_url, page_index)
                    try:
                        response = await self._request(page_url, params=None)
                        _raise_if_access_blocked(response)
                        parser = _ChannelListParser(response.url)
                        parser.feed(response.text)
                        if not parser.found_listing:
                            raise CCGPParseError(
                                "CCGP fallback directory did not contain announcement rows"
                            )
                    except Exception as error:
                        fallback_error = error
                        break
                    fallback_succeeded = True
                    for item in parser.items:
                        if (
                            item.url in seen_urls
                            or not _is_active_procurement_title(item.title)
                            or not _within_time_range(item.published_at, task)
                            or not _region_matches(item.region, task.regions)
                            or not _title_matches_terms(item.title, task, planned_terms)
                        ):
                            continue
                        seen_urls.add(item.url)
                        try:
                            detail_response = await self._request(item.url, params=None)
                            _raise_if_access_blocked(detail_response)
                            notice = self._parse_notice(detail_response, task)
                        except CCGPError as error:
                            logger.warning(
                                "Skipping unavailable CCGP fallback detail %s: %s",
                                item.url,
                                error,
                            )
                            continue
                        if _matches_exclusion(notice, task.exclusions):
                            continue
                        notices.append(notice)
                        if len(notices) >= max_notices:
                            return notices
            if not fallback_succeeded:
                raise CCGPError(
                    "CCGP search and official fallback directories were both unavailable: "
                    f"{fallback_error or last_search_error or 'unknown source response'}"
                ) from (fallback_error or last_search_error)
        return notices

    async def _request(
        self, url: str, *, params: dict[str, Any] | None
    ) -> HTTPResponse:
        if not _is_ccgp_url(url):
            raise CCGPError("refusing to request a non-CCGP URL")
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        }
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            await self._respect_rate_limit()
            try:
                response = await self._transport.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
                if response.status_code == 403:
                    raise CCGPAccessBlockedError(
                        "CCGP refused automated access; no bypass was attempted"
                    )
                if response.status_code == 429:
                    last_error = CCGPTemporaryUnavailableError(
                        "CCGP rate limited the public request"
                    )
                if response.status_code >= 500:
                    last_error = CCGPError(
                        f"CCGP returned transient HTTP {response.status_code}"
                    )
                elif response.status_code >= 400:
                    raise CCGPError(f"CCGP returned HTTP {response.status_code}")
                elif _is_server_busy_response(response):
                    last_error = CCGPTemporaryUnavailableError(
                        "CCGP public search service returned its server-busy page"
                    )
                else:
                    if not _is_ccgp_url(response.url):
                        raise CCGPError("CCGP redirected to a non-CCGP URL")
                    return response
            except CCGPAccessBlockedError:
                raise
            except HTTPError as error:
                if error.code == 403:
                    raise CCGPAccessBlockedError(
                        "CCGP refused automated access; no bypass was attempted"
                    ) from error
                if error.code == 429:
                    last_error = CCGPTemporaryUnavailableError(
                        "CCGP rate limited the public request"
                    )
                    if attempt < self.max_retries:
                        await self._sleep(self.retry_backoff * (2**attempt))
                        continue
                if error.code < 500:
                    raise CCGPError(f"CCGP returned HTTP {error.code}") from error
                last_error = error
            except (TimeoutError, URLError, OSError) as error:
                last_error = error
            if attempt < self.max_retries:
                await self._sleep(self.retry_backoff * (2**attempt))
        if isinstance(last_error, CCGPTemporaryUnavailableError):
            raise CCGPTemporaryUnavailableError(
                f"CCGP search service stayed busy after {self.max_retries + 1} attempts"
            ) from last_error
        detail = f"{type(last_error).__name__}: {last_error}" if last_error else "unknown error"
        raise CCGPError(
            f"CCGP request failed after {self.max_retries + 1} attempts ({detail})"
        ) from last_error

    async def _respect_rate_limit(self) -> None:
        with self._rate_limit_lock:
            current = self._clock()
            earliest = (
                self._last_request_started + self.min_interval
                if self._last_request_started is not None
                else current
            )
            reserved = max(current, earliest)
            wait_for = max(0.0, reserved - current)
            self._last_request_started = reserved
        if wait_for > 0:
            await self._sleep(wait_for)

    def _search_params(
        self,
        task: TaskSpec,
        page_index: int,
        query_region: str,
        *,
        search_term: str | None = None,
    ) -> dict[str, Any]:
        terms = _unique_nonempty([task.topic, *task.keywords])
        start_time, end_time = self._effective_search_range(task)
        return {
            "searchtype": 1,
            "page_index": page_index,
            "bidSort": 0,
            "buyerName": "",
            "projectId": "",
            "pinMu": 0,
            "bidType": 0,
            "dbselect": "bidx",
            "kw": search_term or " ".join(terms),
            "start_time": _search_date(start_time),
            "end_time": _search_date(end_time),
            "timeType": 6 if task.time_range_start or task.time_range_end else 0,
            "displayZone": query_region,
            "zoneId": "",
            "pppStatus": 0,
            "agentName": "",
        }

    def _effective_search_range(
        self,
        task: TaskSpec,
    ) -> tuple[datetime | None, datetime | None]:
        """Keep future monitoring windows valid for CCGP's historical search form."""

        today = self._now().astimezone(SHANGHAI_TZ)
        start = task.time_range_start
        end = task.time_range_end
        if end is not None and end > today:
            end = today
        if start is not None and start > today:
            start = today.replace(hour=0, minute=0, second=0, microsecond=0)
        if start is not None and end is not None and start > end:
            start = end.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, end

    def _parse_notice(self, response: HTTPResponse, task: TaskSpec) -> TenderNotice:
        parser = _DetailParser(response.url)
        parser.feed(response.text)
        title = _clean_text(parser.meta.get("ArticleTitle", ""))
        published_at = _parse_datetime(parser.meta.get("PubDate", ""))
        core_content = _clean_multiline("".join(parser.content_parts))
        if not title:
            raise CCGPParseError("detail page did not disclose a title")
        if published_at is None:
            raise CCGPParseError("detail page did not disclose a publication time")
        if not core_content:
            raise CCGPParseError("detail page did not disclose notice content")

        fetched_at = self._now()
        if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
            raise ValueError("now() must return a timezone-aware datetime")
        table = parser.table_fields
        project_code, project_label = _first_table_value(
            table, ("采购项目编号", "项目编号", "项目号")
        )
        project_quote = project_code
        project_locator = f"公告概要表/{project_label}" if project_label else ""
        if project_code is None:
            project_code, project_quote = _find_project_code(core_content)
            project_locator = ".vF_detail_content" if project_code else ""
        purchaser, purchaser_label = _first_table_value(
            table, ("采购单位", "采购人")
        )
        region, region_label = _first_table_value(table, ("行政区域", "地域"))
        budget_text, budget_label = _first_table_value(
            table, ("预算金额", "采购预算")
        )
        deadline, deadline_quote = _find_labeled_datetime(
            core_content,
            (
                "投标文件递交截止时间",
                "提交投标文件截止时间",
                "响应文件提交截止时间",
            ),
        )
        deadline_locator = ".vF_detail_content"
        if deadline is None:
            deadline_text, deadline_label = _first_table_value(
                table,
                ("投标截止时间", "响应文件提交截止时间"),
            )
            deadline = _parse_datetime(deadline_text)
            deadline_quote = deadline_text
            deadline_locator = (
                f"公告概要表/{deadline_label}" if deadline_label else ""
            )
        budget = _parse_budget(budget_text)
        searchable = f"{title}\n{core_content}".casefold()
        topic_keywords = [
            term
            for term in _unique_nonempty([task.topic, *task.keywords])
            if term.casefold() in searchable
        ]

        evidence: list[EvidenceReference] = []

        def add_evidence(field_path: str, quote: str, locator: str) -> None:
            evidence.append(
                EvidenceReference(
                    evidence_id=f"ccgp-evidence-{field_path}",
                    field_path=field_path,
                    source_url=response.url,
                    locator=locator,
                    quote=quote,
                    fetched_at=fetched_at,
                )
            )

        if project_code and project_quote and project_locator:
            add_evidence("project_code", project_quote, project_locator)
        if region and region_label:
            add_evidence("region", region, f"公告概要表/{region_label}")
        if topic_keywords:
            add_evidence(
                "topic_keywords",
                _supporting_quote(title, core_content, topic_keywords),
                "meta[name='ArticleTitle'], .vF_detail_content",
            )
        if purchaser and purchaser_label:
            add_evidence("purchaser", purchaser, f"公告概要表/{purchaser_label}")
        if budget is not None and budget_label and budget_text:
            add_evidence("budget", budget_text, f"公告概要表/{budget_label}")
        if deadline is not None and deadline_quote and deadline_locator:
            add_evidence("deadline", deadline_quote, deadline_locator)

        attachments = _build_attachments(parser.attachments)
        notice_type = _notice_type(title)
        raw_content = getattr(response, "content", None)
        raw_fingerprint = (
            _sha256_bytes(raw_content)
            if raw_content is not None
            else _sha256(response.text)
        )
        normalized_title = _identity_text(title)
        notice_fingerprint = _sha256(
            "|".join(
                (
                    "ccgp-v1",
                    project_code or "",
                    notice_type,
                    normalized_title,
                    published_at.isoformat(),
                )
            )
        )
        project_fingerprint = _sha256(
            "|".join(
                (
                    "ccgp-project-v1",
                    _identity_text(project_code or ""),
                    _identity_text(purchaser or ""),
                    _project_title(title),
                )
            )
        )
        source_notice_id = _source_notice_id(response.url)

        return TenderNotice(
            notice_id=f"ccgp-{_sha256(response.url)[:24]}",
            notice_type=notice_type,
            project_code=project_code,
            title=title,
            published_at=published_at,
            source=SourceRecord(
                source_id=self.metadata["source_id"],
                source_name=self.metadata["name"],
                source_url=response.url,
                publication_role="original",
                source_notice_id=source_notice_id,
                authority=self.metadata["authority"],
            ),
            core_content=core_content,
            attachments=attachments,
            region=region,
            topic_keywords=topic_keywords,
            purchaser=purchaser,
            budget=budget,
            deadline=deadline,
            raw_content_fingerprint=raw_fingerprint,
            notice_stable_fingerprint=notice_fingerprint,
            project_stable_fingerprint=project_fingerprint,
            fetched_at=fetched_at,
            evidence=evidence,
        )


def _clean_text(value: str) -> str:
    return _SPACE_RE.sub(" ", value.replace("\xa0", " ")).strip()


def _clean_multiline(value: str) -> str:
    lines = [_clean_text(line) for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = _clean_text(value).replace("  ", " ")
    match = re.search(
        r"\d{4}(?:年|[-.])\d{1,2}(?:月|[-.])\d{1,2}(?:日)?(?:\s+\d{1,2}:\d{2})?",
        normalized,
    )
    candidate = match.group(0) if match else normalized
    for pattern in _DATE_PATTERNS:
        try:
            return datetime.strptime(candidate, pattern).replace(tzinfo=SHANGHAI_TZ)
        except ValueError:
            continue
    return None


def _find_datetime(value: str) -> datetime | None:
    return _parse_datetime(value)


def _find_list_region(value: str) -> str | None:
    match = re.search(r"(?:地域|行政区域)\s*[：:]\s*([^\s]+)", value)
    return match.group(1).strip("，,；;") if match else None


def _channel_page_url(channel_url: str, page_index: int) -> str:
    if page_index <= 0:
        return channel_url
    return urljoin(channel_url, f"index_{page_index}.htm")


def _is_active_procurement_title(title: str) -> bool:
    return not re.search(
        r"中标|成交|结果公告|结果公示|候选人|废标|流标|终止|取消",
        title,
    )


def _title_matches_terms(
    title: str,
    task: TaskSpec,
    planned_terms: list[str],
) -> bool:
    folded = title.casefold()
    terms = _unique_nonempty([task.topic, *task.keywords, *planned_terms])
    return not terms or any(term.casefold() in folded for term in terms)


def _find_labeled_datetime(
    value: str, labels: tuple[str, ...]
) -> tuple[datetime | None, str | None]:
    for line in value.splitlines():
        if not any(label in line for label in labels):
            continue
        parsed = _parse_datetime(line)
        if parsed is not None:
            return parsed, line
    return None, None


def _find_project_code(value: str) -> tuple[str | None, str | None]:
    for line in value.splitlines():
        match = re.search(
            r"(?:采购)?项目(?:编号|号)\s*[：:]\s*([^\s，,。；;]+)",
            line,
        )
        if match:
            return match.group(1), line
    return None, None


def _search_date(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(SHANGHAI_TZ).strftime("%Y:%m:%d")


def _within_time_range(value: datetime | None, task: TaskSpec) -> bool:
    if value is None:
        return True
    if task.time_range_start and value < task.time_range_start:
        return False
    if task.time_range_end and value > task.time_range_end:
        return False
    return True


def _region_matches(value: str | None, requested: list[str]) -> bool:
    if not requested or value is None:
        return True
    actual = _identity_text(value)
    return any(
        _identity_text(region) in actual or actual in _identity_text(region)
        for region in requested
        if region.strip()
    )


def _parse_budget(value: str | None) -> Decimal | None:
    if not value:
        return None
    match = re.search(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(亿元|万元|元)", value)
    if not match:
        return None
    try:
        amount = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None
    multiplier = {
        "亿元": Decimal("100000000"),
        "万元": Decimal("10000"),
        "元": Decimal("1"),
    }[match.group(2)]
    return amount * multiplier


def _first_table_value(
    table: Mapping[str, str], labels: tuple[str, ...]
) -> tuple[str | None, str | None]:
    for label in labels:
        value = table.get(label)
        if value:
            return value, label
    return None, None


def _unique_nonempty(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        cleaned = _clean_text(value)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _supporting_quote(title: str, content: str, keywords: list[str]) -> str:
    for line in (title, *content.splitlines()):
        if any(keyword.casefold() in line.casefold() for keyword in keywords):
            return line[:500]
    return title[:500]


def _build_attachments(links: list[_AttachmentLink]) -> list[Attachment]:
    attachments: list[Attachment] = []
    seen: set[str] = set()
    for link in links:
        if link.url in seen:
            continue
        seen.add(link.url)
        media_type, _ = mimetypes.guess_type(urlparse(link.url).path)
        attachments.append(
            Attachment(
                attachment_id=f"ccgp-attachment-{_sha256(link.url)[:20]}",
                name=link.name,
                url=link.url,
                media_type=media_type,
            )
        )
    return attachments


def _looks_like_attachment(url: str, name: str | None) -> bool:
    path = urlparse(url).path.casefold()
    if re.search(r"\.(?:pdf|docx?|xlsx?|zip|rar|7z)(?:$|[?#])", path):
        return True
    text = (name or "").casefold()
    return "附件" in text or "下载" in text


def _notice_type(title: str) -> str:
    if any(word in title for word in ("更正", "变更", "澄清")):
        return "correction"
    if any(word in title for word in ("中标", "成交", "结果公告")):
        return "award"
    if any(word in title for word in ("废标", "终止", "取消")):
        return "cancellation"
    if any(word in title for word in ("招标", "采购", "磋商", "谈判", "询价")):
        return "tender"
    return "other"


def _identity_text(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def _project_title(title: str) -> str:
    value = re.sub(
        r"(?:公开招标|竞争性磋商|竞争性谈判|询价|采购|中标|成交|更正|变更|终止|废标|结果)?公告.*$",
        "",
        title,
    )
    return _identity_text(value or title)


def _source_notice_id(url: str) -> str | None:
    name = urlparse(url).path.rsplit("/", 1)[-1]
    value = re.sub(r"\.s?html?$", "", name, flags=re.IGNORECASE)
    return value or None


def _matches_exclusion(notice: TenderNotice, exclusions: list[str]) -> bool:
    haystack = f"{notice.title}\n{notice.core_content}".casefold()
    return any(term.casefold() in haystack for term in exclusions if term.strip())


def _is_server_busy_response(response: HTTPResponse) -> bool:
    path = urlparse(response.url).path.casefold()
    sample = response.text[:3000]
    return "serverisbusy" in path or "您正在访问中国政府采购网搜索平台" in sample


def _raise_if_access_blocked(response: HTTPResponse) -> None:
    sample = response.text[:5000]
    strong_markers = ("频繁访问!中国政府采购网", "您的访问过于频繁", "请输入验证码")
    security_page = "安全验证" in sample and not any(
        marker in sample
        for marker in ("vT-srch-result-list-bid", "vF_detail_content")
    )
    if response.status_code in {403, 429} or any(
        marker in sample for marker in strong_markers
    ) or security_page:
        raise CCGPAccessBlockedError(
            "CCGP requested that automated access stop; no bypass was attempted"
        )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_ccgp_url(value: str) -> bool:
    if not _is_http_url(value):
        return False
    hostname = (urlparse(value).hostname or "").casefold()
    return hostname == "ccgp.gov.cn" or hostname.endswith(".ccgp.gov.cn")
