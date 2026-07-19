"""Collector for the public pages of the National Public Resource Trading Platform.

The adapter deliberately uses only anonymous, publicly accessible endpoints.  It
does not solve captchas, replay cookies, or attempt to disguise automated access.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha256
from html.parser import HTMLParser
import json
import re
import socket
import time
from typing import Any, Awaitable, Callable, Iterable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
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
SEARCH_URL = "https://www.ggzy.gov.cn/information/pubTradingInfo/getTradList"
SEARCH_PAGE_URL = "https://www.ggzy.gov.cn/deal/dealList.html"
PUBLIC_BASE_URL = "https://www.ggzy.gov.cn/"
DEFAULT_USER_AGENT = "BidRadar-X/1.0 (public tender notice collector)"
OPEN_RANGE_START = date(2000, 1, 1)

PROVINCE_CODES = {
    "北京": "110000",
    "天津": "120000",
    "河北": "130000",
    "山西": "140000",
    "内蒙古": "150000",
    "辽宁": "210000",
    "吉林": "220000",
    "黑龙江": "230000",
    "上海": "310000",
    "江苏": "320000",
    "浙江": "330000",
    "安徽": "340000",
    "福建": "350000",
    "江西": "360000",
    "山东": "370000",
    "河南": "410000",
    "湖北": "420000",
    "湖南": "430000",
    "广东": "440000",
    "广西": "450000",
    "海南": "460000",
    "重庆": "500000",
    "四川": "510000",
    "贵州": "520000",
    "云南": "530000",
    "西藏": "540000",
    "陕西": "610000",
    "甘肃": "620000",
    "青海": "630000",
    "宁夏": "640000",
    "新疆": "650000",
    "兵团": "660000",
}


class GGZYSourceError(RuntimeError):
    """Base class for explicit, non-silent source failures."""


class GGZYStructureChangedError(GGZYSourceError):
    """The response no longer contains the public fields the parser requires."""


class GGZYTimeoutError(GGZYSourceError):
    """The public endpoint did not answer within the configured deadline."""


class GGZYAccessRestrictedError(GGZYSourceError):
    """The platform requested human verification or rejected anonymous access."""


class GGZYHTTPError(GGZYSourceError):
    """The public endpoint returned an unexpected HTTP/network failure."""


@dataclass(frozen=True)
class GGZYHTTPResponse:
    status: int
    url: str
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)

    def text(self) -> str:
        content_type = self.headers.get("content-type", self.headers.get("Content-Type", ""))
        charset_match = re.search(r"charset=([\w-]+)", content_type, re.IGNORECASE)
        encodings = [charset_match.group(1)] if charset_match else []
        encodings.extend(["utf-8-sig", "gb18030"])
        for encoding in dict.fromkeys(encodings):
            try:
                return self.body.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
        raise GGZYStructureChangedError("response text encoding could not be decoded")


class GGZYTransport(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None,
        headers: dict[str, str],
        timeout: float,
    ) -> GGZYHTTPResponse:
        ...


class _UrllibTransport:
    async def request(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None,
        headers: dict[str, str],
        timeout: float,
    ) -> GGZYHTTPResponse:
        return await asyncio.to_thread(
            self._request_sync,
            method,
            url,
            data,
            headers,
            timeout,
        )

    @staticmethod
    def _request_sync(
        method: str,
        url: str,
        data: dict[str, str] | None,
        headers: dict[str, str],
        timeout: float,
    ) -> GGZYHTTPResponse:
        encoded_data = urlencode(data).encode("utf-8") if data is not None else None
        request = Request(url, data=encoded_data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                return GGZYHTTPResponse(
                    status=response.status,
                    url=response.geturl(),
                    body=response.read(),
                    headers=dict(response.headers.items()),
                )
        except HTTPError as error:
            return GGZYHTTPResponse(
                status=error.code,
                url=error.geturl(),
                body=error.read(),
                headers=dict(error.headers.items()) if error.headers else {},
            )


@dataclass(frozen=True)
class GGZYSearchResult:
    title: str
    source_url: str
    published_at: datetime | None
    region: str | None
    source_name: str | None
    source_notice_id: str | None
    canonical_notice_url: str | None = None
    region_field: str | None = None
    region_evidence_quote: str | None = None
    source_name_field: str | None = None
    source_name_evidence_quote: str | None = None


@dataclass(frozen=True)
class GGZYSearchPage:
    results: list[GGZYSearchResult]
    total_pages: int | None


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[_Node | str] = field(default_factory=list)

    def iter_nodes(self) -> Iterable[_Node]:
        yield self
        for child in self.children:
            if isinstance(child, _Node):
                yield from child.iter_nodes()

    def text(self, separator: str = " ") -> str:
        chunks: list[str] = []
        for child in self.children:
            if isinstance(child, str):
                chunks.append(child)
            else:
                value = child.text(separator)
                if value:
                    chunks.append(value)
        return separator.join(chunks)


class _HTMLTreeParser(HTMLParser):
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

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document")
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag.lower(), {key.lower(): value or "" for key, value in attrs})
        self._stack[-1].children.append(node)
        if node.tag not in self._VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self._VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self._stack[-1].children.append(data)


def _clean_inline(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clean_block(value: str) -> str:
    lines = [_clean_inline(line) for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def _node_marker(node: _Node) -> str:
    return f"{node.attrs.get('id', '')} {node.attrs.get('class', '')}".lower()


def _find_content_node(root: _Node) -> _Node | None:
    exact_markers = (
        "detail-content",
        "detail_content",
        "detailcontent",
        "article-content",
        "article_content",
        "ewb-article-info",
        "contentdiv",
        "vF_detail_content".lower(),
    )
    candidates = [
        node
        for node in root.iter_nodes()
        if node.tag in {"article", "div", "section"}
        and any(marker in _node_marker(node) for marker in exact_markers)
    ]
    if not candidates:
        candidates = [node for node in root.iter_nodes() if node.tag == "article"]
    return max(candidates, key=lambda node: len(_clean_inline(node.text())), default=None)


def _find_embedded_notice_url(
    html: str,
    source_url: str,
    source_notice_id: str | None = None,
) -> str | None:
    script_match = re.search(
        r"firstLastUrl\s*=\s*['\"]([^'\"]+)['\"]",
        html,
        flags=re.IGNORECASE,
    )
    if script_match:
        resolved = urljoin(source_url, script_match.group(1))
        if resolved.startswith(("https://", "http://")) and resolved != source_url:
            return resolved

    # Current GGZY aggregate pages load the real notice body through
    # ``showDetail(..., '/information/deal/html/b/...')`` rather than an
    # iframe. Prefer the URL carrying the current search-record id because an
    # aggregate page can also list later corrections and result notices.
    embedded_paths = re.findall(
        r"['\"](/information/deal/html/b/[^'\"]+\.html)['\"]",
        html,
        flags=re.IGNORECASE,
    )
    if embedded_paths:
        selected = next(
            (
                value
                for value in embedded_paths
                if source_notice_id and source_notice_id in value
            ),
            embedded_paths[0],
        )
        resolved = urljoin(source_url, selected)
        if resolved != source_url:
            return resolved

    parser = _HTMLTreeParser()
    parser.feed(html)
    for node in parser.root.iter_nodes():
        candidate: str | None = None
        if node.tag == "iframe":
            candidate = node.attrs.get("src")
        elif node.tag == "a" and re.search(
            r"原文|来源|查看公告|公告详情", _clean_inline(node.text())
        ):
            candidate = node.attrs.get("href")
        if not candidate:
            continue
        resolved = urljoin(source_url, candidate)
        if resolved.startswith(("https://", "http://")) and resolved != source_url:
            return resolved
    return None


def _first_match(pattern: str, value: str) -> str | None:
    match = re.search(pattern, value, flags=re.IGNORECASE)
    return _clean_inline(match.group(1)) if match else None


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None:
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=SHANGHAI_TZ)

    normalized = value.strip().replace("年", "-").replace("月", "-").replace("日", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    for pattern in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(normalized, pattern).replace(tzinfo=SHANGHAI_TZ)
        except ValueError:
            continue
    raise GGZYStructureChangedError(f"unsupported publication time: {value!r}")


def _mapping_value(item: Mapping[str, Any], *keys: str) -> Any:
    folded = {str(key).casefold(): value for key, value in item.items()}
    for key in keys:
        value = folded.get(key.casefold())
        if value not in (None, ""):
            return value
    return None


def _mapping_entry(
    item: Mapping[str, Any], *keys: str
) -> tuple[str, Any] | tuple[None, None]:
    wanted = {key.casefold() for key in keys}
    for actual_key, value in item.items():
        if str(actual_key).casefold() in wanted and value not in (None, ""):
            return str(actual_key), value
    return None, None


def _province_code(region: str | None) -> str:
    if not region:
        return "0"
    compact = re.sub(r"\s+", "", region)
    for name, code in PROVINCE_CODES.items():
        if compact.startswith(name):
            return code
    return "0"


def _normalize_region_text(value: str) -> str:
    normalized = re.sub(r"\s+", "", value).casefold()
    for suffix in (
        "壮族自治区",
        "回族自治区",
        "维吾尔自治区",
        "自治区",
        "特别行政区",
        "省",
        "市",
        "地区",
        "自治州",
        "区",
        "县",
    ):
        normalized = normalized.replace(suffix, "")
    return normalized


def _matches_requested_region(notice: TenderNotice, requested_regions: list[str]) -> bool:
    if not requested_regions:
        return True
    searchable = _normalize_region_text(
        " ".join(
            value
            for value in (notice.region, notice.title, notice.core_content)
            if value
        )
    )
    return any(
        normalized and normalized in searchable
        for region in requested_regions
        if (normalized := _normalize_region_text(region))
    )


def _looks_restricted(status: int, text: str) -> bool:
    if status in {401, 403, 407, 429, 451}:
        return True
    compact = _clean_inline(text).casefold()
    markers = (
        "验证码",
        "安全验证",
        "访问频繁",
        "请求过于频繁",
        "访问受限",
        "拒绝访问",
        "access denied",
        "forbidden",
        "captcha",
    )
    return any(marker in compact for marker in markers)


def parse_search_response(payload: bytes | str | Mapping[str, Any]) -> GGZYSearchPage:
    """Parse one documented public search response without depending on key casing."""

    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = payload.decode("gb18030")
        if _looks_restricted(200, text):
            raise GGZYAccessRestrictedError("platform requested human verification")
        try:
            decoded: Any = json.loads(text)
        except json.JSONDecodeError as error:
            raise GGZYStructureChangedError("search response is not valid JSON") from error
    elif isinstance(payload, str):
        if _looks_restricted(200, payload):
            raise GGZYAccessRestrictedError("platform requested human verification")
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as error:
            raise GGZYStructureChangedError("search response is not valid JSON") from error
    else:
        decoded = payload

    if not isinstance(decoded, Mapping):
        raise GGZYStructureChangedError("search response root is not an object")

    response_code = _mapping_value(decoded, "code", "status", "statusCode")
    response_message = str(_mapping_value(decoded, "msg", "message") or "")
    if response_code is not None and str(response_code) not in {"0", "200"}:
        if str(response_code) in {"401", "403", "407", "429", "451", "829"} or _looks_restricted(200, response_message):
            raise GGZYAccessRestrictedError(
                response_message or "platform requested human verification"
            )
        raise GGZYStructureChangedError(
            f"search API returned code {response_code}: {response_message or 'unknown error'}"
        )

    raw_data = _mapping_value(decoded, "data", "rows", "records", "list")
    nested_meta: Mapping[str, Any] = {}
    if isinstance(raw_data, Mapping):
        nested_meta = raw_data
        raw_data = _mapping_value(raw_data, "rows", "records", "list", "data")
    if raw_data is None:
        raise GGZYStructureChangedError("search response has no result collection")
    if not isinstance(raw_data, list):
        raise GGZYStructureChangedError("search result collection is not a list")

    total_value = _mapping_value(
        decoded,
        "ttlpage",
        "totalPage",
        "totalPages",
        "pageCount",
        "pages",
    )
    if total_value is None:
        total_value = _mapping_value(
            nested_meta,
            "ttlpage",
            "totalPage",
            "totalPages",
            "pageCount",
            "pages",
        )
    total_pages: int | None = None
    if total_value is not None:
        try:
            total_pages = max(int(total_value), 0)
        except (TypeError, ValueError) as error:
            raise GGZYStructureChangedError("search page count is not numeric") from error

    results: list[GGZYSearchResult] = []
    for index, raw_item in enumerate(raw_data):
        if not isinstance(raw_item, Mapping):
            raise GGZYStructureChangedError(f"search result {index} is not an object")
        title = _mapping_value(raw_item, "title", "noticeTitle", "projectName")
        link = _mapping_value(raw_item, "url", "linkurl", "linkUrl", "detailUrl", "href")
        if not title or not link:
            raise GGZYStructureChangedError(
                f"search result {index} is missing title or detail URL"
            )
        published_value = _mapping_value(
            raw_item,
            "timeShow",
            "publishTime",
            "publishedAt",
            "date",
        )
        published_at = _parse_datetime(str(published_value)) if published_value else None
        canonical = _mapping_value(
            raw_item,
            "sourceUrl",
            "originUrl",
            "canonicalUrl",
            "originalUrl",
        )
        region_field, region_value = _mapping_entry(
            raw_item, "provinceText", "province", "region", "area"
        )
        source_name_field, source_name_value = _mapping_entry(
            raw_item,
            "platform",
            "platformName",
            "sourceName",
            "transactionSourcesPlatformText",
        )
        results.append(
            GGZYSearchResult(
                title=_clean_inline(str(title)),
                source_url=urljoin(PUBLIC_BASE_URL, str(link)),
                published_at=published_at,
                region=_clean_inline(str(region_value)) if region_value else None,
                source_name=(
                    _clean_inline(str(source_name_value)) if source_name_value else None
                ),
                source_notice_id=(
                    str(value)
                    if (value := _mapping_value(raw_item, "id", "noticeId", "infoid"))
                    else None
                ),
                canonical_notice_url=(
                    urljoin(PUBLIC_BASE_URL, str(canonical)) if canonical else None
                ),
                region_field=region_field,
                region_evidence_quote=(
                    json.dumps(
                        {region_field: region_value},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    if region_field
                    else None
                ),
                source_name_field=source_name_field,
                source_name_evidence_quote=(
                    json.dumps(
                        {source_name_field: source_name_value},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    if source_name_field
                    else None
                ),
            )
        )
    return GGZYSearchPage(results=results, total_pages=total_pages)


def _notice_type(title: str) -> str:
    if re.search(r"更正|变更|澄清|答疑", title):
        return "correction"
    if re.search(r"中标|成交|结果|候选人", title):
        return "award"
    if re.search(r"终止|废标|流标|取消", title):
        return "cancellation"
    return "tender"


def _looks_like_active_procurement_title(title: str) -> bool:
    """Reject lifecycle-complete and asset-trading rows before detail parsing."""

    return not re.search(
        r"中标|成交|结果公示|候选人|废标|流标|终止|取消|"
        r"转让|拍卖|挂牌(?:披露|出让)|出租|竞价",
        title,
    )


def _fingerprint(*values: str) -> str:
    normalized = "\x1f".join(_clean_inline(value).casefold() for value in values)
    return sha256(normalized.encode("utf-8")).hexdigest()


class GGZYSource:
    """Parse and collect anonymous public GGZY notices into ``TenderNotice``."""

    metadata = {
        "source_id": "ggzy-national",
        "name": "全国公共资源交易平台",
        "authority": 1.0,
        "requires_login": False,
    }

    def __init__(
        self,
        *,
        transport: GGZYTransport | None = None,
        timeout: float = 15.0,
        retries: int = 1,
        request_interval: float = 0.25,
        retry_backoff: float = 0.75,
        max_pages: int = 100,
        now: Callable[[], datetime] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if retries < 0:
            raise ValueError("retries must not be negative")
        if request_interval < 0:
            raise ValueError("request_interval must not be negative")
        if retry_backoff < 0:
            raise ValueError("retry_backoff must not be negative")
        if max_pages < 1:
            raise ValueError("max_pages must be at least one")
        self._transport = transport or _UrllibTransport()
        self._timeout = timeout
        self._retries = retries
        self._request_interval = request_interval
        self._retry_backoff = retry_backoff
        self._max_pages = max_pages
        self._now = now or (lambda: datetime.now(tz=SHANGHAI_TZ))
        self._sleep = sleep
        self._last_request_at: float | None = None

    async def collect(
        self,
        task_spec: TaskSpec | Mapping[str, Any],
        search_plan: Mapping[str, Any] | None = None,
    ) -> list[TenderNotice]:
        task = (
            task_spec
            if isinstance(task_spec, TaskSpec)
            else TaskSpec.model_validate(task_spec)
        )
        plan = dict(search_plan or {})
        max_pages = min(
            max(int(plan.get("max_pages", self._max_pages)), 1),
            self._max_pages,
        )
        max_results = min(
            max(int(plan.get("max_results_per_source", 24)), 1),
            60,
        )
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now() must return a timezone-aware datetime")

        today = now.astimezone(SHANGHAI_TZ).date()
        if task.time_range_start is not None:
            start_date = task.time_range_start.date()
        elif task.time_range_end is not None:
            start_date = min(OPEN_RANGE_START, task.time_range_end.date())
        else:
            start_date = today
        if task.time_range_end is not None:
            end_date = task.time_range_end.date()
        elif task.time_range_start is not None:
            end_date = max(today, task.time_range_start.date())
        else:
            end_date = today
        topic = _clean_inline(str(plan.get("query") or task.topic))
        planned_topics = [
            _clean_inline(str(value))
            for value in plan.get("search_terms", [])
            if _clean_inline(str(value))
        ][:6]
        search_topics = list(dict.fromkeys(planned_topics)) or [topic]
        topic_terms = list(
            dict.fromkeys(
                cleaned
                for value in [topic, *task.keywords]
                if (cleaned := _clean_inline(value))
            )
        )
        requested_regions = task.regions or [None]
        detail_results: dict[str, tuple[GGZYSearchResult, dict[str, str]]] = {}
        successful_search_requests = 0
        last_search_error: GGZYSourceError | None = None

        for requested_region in requested_regions:
            if len(detail_results) >= max_results:
                break
            for search_topic in search_topics:
                if len(detail_results) >= max_results:
                    break
                page_number = 1
                while page_number <= max_pages:
                    form = self._search_form(
                        topic=search_topic,
                        region=requested_region,
                        start_date=start_date.isoformat(),
                        end_date=end_date.isoformat(),
                        page_number=page_number,
                        plan=plan,
                    )
                    try:
                        response = await self._request("POST", SEARCH_URL, data=form)
                        search_page = parse_search_response(response.body)
                    except GGZYSourceError as error:
                        last_search_error = error
                        break
                    successful_search_requests += 1
                    for result in search_page.results:
                        detail_results.setdefault(result.source_url, (result, dict(form)))
                        if len(detail_results) >= max_results:
                            break

                    if len(detail_results) >= max_results:
                        break
                    if not search_page.results:
                        break
                    if (
                        search_page.total_pages is not None
                        and page_number >= search_page.total_pages
                    ):
                        break
                    page_number += 1
                else:
                    raise GGZYSourceError(
                        f"search exceeded the configured max_pages={max_pages}"
                    )

        if successful_search_requests == 0 and last_search_error is not None:
            raise last_search_error

        notices: list[TenderNotice] = []
        successful_detail_requests = 0
        last_detail_error: GGZYSourceError | None = None
        for result, search_form in detail_results.values():
            if not _looks_like_active_procurement_title(result.title):
                continue
            try:
                response = await self._request("GET", result.source_url, data=None)
                detail_html = response.text()
                canonical_notice_url = (
                    result.canonical_notice_url
                    or _find_embedded_notice_url(
                        detail_html,
                        result.source_url,
                        result.source_notice_id,
                    )
                )
                notice_html = detail_html
                content_base_url = None
                if canonical_notice_url:
                    original_response = await self._request(
                        "GET", canonical_notice_url, data=None
                    )
                    notice_html = original_response.text()
                    content_base_url = canonical_notice_url
                notice = self.parse_notice_html(
                    notice_html,
                    source_url=result.source_url,
                    region=result.region,
                    region_evidence_url=SEARCH_URL,
                    region_evidence_quote=result.region_evidence_quote,
                    region_evidence_locator=self._search_evidence_locator(
                        search_form,
                        result.source_notice_id,
                        result.region_field,
                    ),
                    source_name_evidence_url=SEARCH_URL,
                    source_name_evidence_quote=result.source_name_evidence_quote,
                    source_name_evidence_locator=self._search_evidence_locator(
                        search_form,
                        result.source_notice_id,
                        result.source_name_field,
                    ),
                    topic_terms=topic_terms,
                    published_at=result.published_at,
                    source_name=result.source_name,
                    source_notice_id=result.source_notice_id,
                    canonical_notice_url=canonical_notice_url,
                    content_base_url=content_base_url,
                )
            except GGZYSourceError as error:
                last_detail_error = error
                continue
            successful_detail_requests += 1
            if topic_terms and not notice.topic_keywords:
                continue
            if not _matches_requested_region(notice, task.regions):
                continue
            if task.exclusions and any(
                exclusion.casefold() in f"{notice.title}\n{notice.core_content}".casefold()
                for exclusion in task.exclusions
            ):
                continue
            if (
                task.time_range_start is not None
                and notice.published_at < task.time_range_start
            ) or (
                task.time_range_end is not None
                and notice.published_at > task.time_range_end
            ):
                continue
            notices.append(notice)
        if detail_results and successful_detail_requests == 0 and last_detail_error is not None:
            raise last_detail_error
        return notices

    @staticmethod
    def _search_evidence_locator(
        form: Mapping[str, str],
        source_notice_id: str | None,
        field_name: str | None,
    ) -> str | None:
        if not field_name:
            return None
        return json.dumps(
            {
                "method": "POST",
                "form": dict(form),
                "source_notice_id": source_notice_id,
                "field": field_name,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _search_form(
        *,
        topic: str,
        region: str | None,
        start_date: str,
        end_date: str,
        page_number: int,
        plan: Mapping[str, Any],
    ) -> dict[str, str]:
        form = {
            "TIMEBEGIN": start_date,
            "TIMEEND": end_date,
            "SOURCE_TYPE": str(plan.get("source_type", "1")),
            "DEAL_TIME": str(plan.get("deal_time", "06")),
            "DEAL_STAGE": str(plan.get("deal_stage", "0001")),
            "PAGENUMBER": str(page_number),
            "FINDTXT": topic,
        }
        optional_filters = {
            "DEAL_CLASSIFY": str(plan.get("deal_classify", "00")),
            "DEAL_PROVINCE": _province_code(region),
            "DEAL_CITY": str(plan.get("deal_city", "0")),
            "DEAL_PLATFORM": str(plan.get("deal_platform", "0")),
            "BID_PLATFORM": str(plan.get("bid_platform", "0")),
            "DEAL_TRADE": str(plan.get("deal_trade", "0")),
        }
        form.update(
            {
                key: value
                for key, value in optional_filters.items()
                if value not in {"0", "00", ""}
            }
        )
        return form

    async def _request(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None,
    ) -> GGZYHTTPResponse:
        if self._last_request_at is not None and self._request_interval:
            remaining = self._request_interval - (time.monotonic() - self._last_request_at)
            if remaining > 0:
                await self._sleep(remaining)

        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Referer": SEARCH_PAGE_URL,
            "X-Pass-Token": "",
        }
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

        for attempt in range(self._retries + 1):
            try:
                response = await asyncio.wait_for(
                    self._transport.request(
                        method,
                        url,
                        data=data,
                        headers=headers,
                        timeout=self._timeout,
                    ),
                    timeout=self._timeout + 1,
                )
                self._last_request_at = time.monotonic()
            except (TimeoutError, asyncio.TimeoutError, socket.timeout) as error:
                if attempt < self._retries:
                    await self._sleep(self._retry_backoff * (2**attempt))
                    continue
                raise GGZYTimeoutError(f"request timed out: {url}") from error
            except URLError as error:
                if isinstance(error.reason, (TimeoutError, socket.timeout)):
                    if attempt < self._retries:
                        await self._sleep(self._retry_backoff * (2**attempt))
                        continue
                    raise GGZYTimeoutError(f"request timed out: {url}") from error
                if attempt < self._retries:
                    await self._sleep(self._retry_backoff * (2**attempt))
                    continue
                raise GGZYHTTPError(
                    f"network request failed after {self._retries + 1} attempts: "
                    f"{type(error.reason).__name__}: {error.reason}"
                ) from error

            text = response.text()
            if _looks_restricted(response.status, text):
                raise GGZYAccessRestrictedError(
                    "platform denied anonymous access or requested human verification"
                )
            if response.status >= 500 and attempt < self._retries:
                await self._sleep(self._retry_backoff * (2**attempt))
                continue
            if response.status < 200 or response.status >= 300:
                raise GGZYHTTPError(
                    f"unexpected HTTP status {response.status} for {url}"
                )
            return response
        raise AssertionError("request retry loop exited unexpectedly")

    def parse_notice_html(
        self,
        html: str,
        *,
        source_url: str,
        region: str | None = None,
        topic_terms: Iterable[str] = (),
        published_at: datetime | str | None = None,
        source_name: str | None = None,
        source_notice_id: str | None = None,
        canonical_notice_url: str | None = None,
        content_base_url: str | None = None,
        region_evidence_url: str | None = None,
        region_evidence_quote: str | None = None,
        region_evidence_locator: str | None = None,
        source_name_evidence_url: str | None = None,
        source_name_evidence_quote: str | None = None,
        source_name_evidence_locator: str | None = None,
    ) -> TenderNotice:
        parser = _HTMLTreeParser()
        parser.feed(html)
        root = parser.root
        content_node = _find_content_node(root)
        if content_node is None:
            raise GGZYStructureChangedError("notice content container was not found")

        content = _clean_block(content_node.text("\n"))
        if not content:
            raise GGZYStructureChangedError("notice content container is empty")

        heading_nodes = [
            node
            for node in root.iter_nodes()
            if node.tag in {"h1", "h2", "h3", "h4"} and _clean_inline(node.text())
        ]
        title_node = next(
            (node for node in heading_nodes if "title" in _node_marker(node)),
            heading_nodes[0] if heading_nodes else None,
        )
        title = _clean_inline(title_node.text()) if title_node else ""
        if not title:
            raise GGZYStructureChangedError("notice title was not found")

        page_text = _clean_block(root.text("\n"))
        published_text = _first_match(
            r"(?:发布时间|发布日期|公告时间)\s*[：:]\s*"
            r"(\d{4}[-年/]\d{1,2}[-月/]\d{1,2}(?:[日\s]+\d{1,2}:\d{2}(?::\d{2})?)?)",
            page_text,
        )
        if published_text is not None:
            parsed_published_at = _parse_datetime(published_text)
        elif isinstance(published_at, datetime):
            parsed_published_at = published_at
        elif isinstance(published_at, str):
            parsed_published_at = _parse_datetime(published_at)
        else:
            raise GGZYStructureChangedError("notice publication time was not found")
        if parsed_published_at.tzinfo is None or parsed_published_at.utcoffset() is None:
            parsed_published_at = parsed_published_at.replace(tzinfo=SHANGHAI_TZ)

        project_code = _first_match(
            r"(?:采购项目编号|项目编号|招标编号)\s*[：:]\s*([A-Za-z0-9][A-Za-z0-9._/()（）-]*)",
            page_text,
        )
        purchaser = _first_match(
            r"(?:采购人(?:名称)?|招标人|采购单位)\s*[：:]\s*([^\s，,；;。]+)",
            content,
        )
        original_source_name = _first_match(r"信息来源\s*[：:]\s*([^\n]+)", page_text)
        reported_original_source_name = original_source_name or source_name
        fetched_at = self._now()
        if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
            raise ValueError("now() must return a timezone-aware datetime")

        attachments: list[Attachment] = []
        seen_attachment_urls: set[str] = set()
        for node in content_node.iter_nodes():
            if node.tag != "a" or not node.attrs.get("href"):
                continue
            link_text = _clean_inline(node.text())
            href = urljoin(content_base_url or canonical_notice_url or source_url, node.attrs["href"])
            if not (
                re.search(r"\.(?:pdf|docx?|xlsx?|zip|rar)(?:$|[?#])", href, re.IGNORECASE)
                or re.search(r"附件|下载|采购文件|招标文件", link_text)
            ):
                continue
            if href in seen_attachment_urls:
                continue
            seen_attachment_urls.add(href)
            attachments.append(
                Attachment(
                    attachment_id=f"attachment-{_fingerprint(href)[:20]}",
                    name=link_text or None,
                    url=href,
                )
            )

        matched_terms = [
            term
            for term in dict.fromkeys(_clean_inline(term) for term in topic_terms)
            if term and term.casefold() in f"{title}\n{content}".casefold()
        ]

        evidence: list[EvidenceReference] = []

        extracted_evidence_url = content_base_url or canonical_notice_url or source_url

        def add_evidence(
            field_path: str,
            quote: str,
            locator: str,
            evidence_url: str,
        ) -> None:
            evidence.append(
                EvidenceReference(
                    evidence_id=f"evidence-{field_path.replace('_', '-')}",
                    field_path=field_path,
                    source_url=evidence_url,
                    locator=locator,
                    quote=quote,
                    fetched_at=fetched_at,
                )
            )

        if project_code:
            add_evidence(
                "project_code",
                f"采购项目编号：{project_code}",
                "公告元数据",
                extracted_evidence_url,
            )
        if region:
            if not region_evidence_quote or not region_evidence_locator:
                raise GGZYStructureChangedError(
                    "region requires its original source field and locator"
                )
            add_evidence(
                "region",
                region_evidence_quote,
                region_evidence_locator,
                region_evidence_url or source_url,
            )
        if matched_terms:
            term = matched_terms[0]
            quote_source = title if term.casefold() in title.casefold() else content
            start = max(quote_source.casefold().find(term.casefold()) - 30, 0)
            add_evidence(
                "topic_keywords",
                quote_source[start : start + 100],
                "标题或公告正文",
                extracted_evidence_url,
            )
        if purchaser:
            add_evidence(
                "purchaser",
                f"采购人：{purchaser}",
                "公告正文",
                extracted_evidence_url,
            )
        if reported_original_source_name:
            if original_source_name:
                original_source_quote = f"信息来源：{original_source_name}"
                original_source_locator = "页面文本标签：信息来源"
                original_source_evidence_url = extracted_evidence_url
            else:
                if not source_name_evidence_quote or not source_name_evidence_locator:
                    raise GGZYStructureChangedError(
                        "source name requires its original source field and locator"
                    )
                original_source_quote = source_name_evidence_quote
                original_source_locator = source_name_evidence_locator
                original_source_evidence_url = source_name_evidence_url or source_url
            add_evidence(
                "source.original_source_name",
                original_source_quote,
                original_source_locator,
                original_source_evidence_url,
            )

        kind = _notice_type(title)
        raw_fingerprint = sha256(html.encode("utf-8")).hexdigest()
        notice_fingerprint = _fingerprint(
            project_code or "", kind, title, parsed_published_at.date().isoformat()
        )
        project_title = re.sub(
            r"(?:招标|采购|资格预审|中标|成交|结果|更正|变更|澄清|答疑|终止|废标|流标|取消|候选人|公告|公示|（|）|\(|\))",
            "",
            title,
        )
        project_fingerprint = (
            _fingerprint(project_code)
            if project_code
            else _fingerprint(purchaser or "", project_title)
        )

        return TenderNotice(
            notice_id=(
                f"ggzy-{source_notice_id}"
                if source_notice_id
                else f"ggzy-{_fingerprint(source_url)[:24]}"
            ),
            notice_type=kind,
            project_code=project_code,
            title=title,
            published_at=parsed_published_at,
            source=SourceRecord(
                source_id=self.metadata["source_id"],
                source_name=self.metadata["name"],
                source_url=source_url,
                publication_role=(
                    "republication"
                    if reported_original_source_name or canonical_notice_url
                    else "original"
                ),
                canonical_notice_url=canonical_notice_url,
                source_notice_id=source_notice_id,
                authority=self.metadata["authority"],
            ),
            core_content=content,
            attachments=attachments,
            region=region,
            topic_keywords=matched_terms,
            purchaser=purchaser,
            raw_content_fingerprint=raw_fingerprint,
            notice_stable_fingerprint=notice_fingerprint,
            project_stable_fingerprint=project_fingerprint,
            fetched_at=fetched_at,
            evidence=evidence,
        )


__all__ = [
    "GGZYAccessRestrictedError",
    "GGZYHTTPError",
    "GGZYHTTPResponse",
    "GGZYSearchPage",
    "GGZYSearchResult",
    "GGZYSource",
    "GGZYSourceError",
    "GGZYStructureChangedError",
    "GGZYTimeoutError",
    "parse_search_response",
]
