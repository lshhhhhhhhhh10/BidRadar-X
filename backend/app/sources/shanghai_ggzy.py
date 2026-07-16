"""Shanghai Public Resources Trading Platform official-list adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import re
from typing import Any, Mapping, Protocol
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from app.schemas.tender import (
    EvidenceReference,
    SourceRecord,
    TaskSpec,
    TenderNotice,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_BASE_URL = "https://www.shggzy.com/"
_LIST_URL = "https://www.shggzy.com/search/queryContents.jhtml"
_CONFLICTS = (
    "中标候选人",
    "中标结果",
    "成交候选",
    "成交结果",
    "成交公告",
    "合同公告",
    "履约验收",
    "终止公告",
    "废标公告",
    "流标公告",
    "取消公告",
    "异常公告",
)


class ShanghaiGGZYSourceError(RuntimeError):
    """Raised when Shanghai's official source cannot be collected safely."""


class ShanghaiGGZYStructureChangedError(ShanghaiGGZYSourceError):
    """Raised when a public page no longer satisfies the verified contract."""


@dataclass(frozen=True)
class HTTPResponse:
    url: str
    text: str
    status_code: int = 200


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
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read(10_000_001)
            if len(body) > 10_000_000:
                raise ShanghaiGGZYSourceError("Shanghai response exceeded 10 MB")
            charset = response.headers.get_content_charset() or "utf-8"
            return HTTPResponse(
                url=response.geturl(),
                text=body.decode(charset, errors="replace"),
                status_code=response.status,
            )


@dataclass(frozen=True)
class _ListItem:
    detail_url: str
    title: str
    project_code: str | None
    published_at: datetime


class _ListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found_list = False
        self.channel_ids: set[str] = set()
        self.items: list[_ListItem] = []
        self._list_depth = 0
        self._in_item = False
        self._detail_path: str | None = None
        self._span_parts: list[str] | None = None
        self._spans: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if (
            tag == "input"
            and attributes.get("name") == "channelId"
            and attributes.get("value")
        ):
            self.channel_ids.add(attributes["value"] or "")
        if tag == "div" and attributes.get("id") == "allList" and not self._list_depth:
            self.found_list = True
            self._list_depth = 1
            return
        if self._list_depth:
            if tag == "div":
                self._list_depth += 1
            if tag == "li" and attributes.get("onclick"):
                path = _onclick_path(attributes["onclick"] or "")
                if path:
                    self._in_item = True
                    self._detail_path = path
                    self._spans = []
            elif self._in_item and tag == "span":
                self._span_parts = []

    def handle_data(self, data: str) -> None:
        if self._span_parts is not None:
            self._span_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._span_parts is not None and tag == "span":
            self._spans.append(_clean_inline(" ".join(self._span_parts)))
            self._span_parts = None
        if self._in_item and tag == "li":
            self._finish_item()
            self._in_item = False
        if self._list_depth and tag == "div":
            self._list_depth -= 1

    def _finish_item(self) -> None:
        values = [value for value in self._spans if value]
        if not self._detail_path or len(values) < 3:
            return
        published_at = _parse_date(values[-1])
        if published_at is None:
            return
        self.items.append(
            _ListItem(
                detail_url=urljoin(_BASE_URL, self._detail_path),
                title=values[0],
                project_code=values[1] or None,
                published_at=published_at,
            )
        )


class _DetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._content_depth = 0
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "div" and "content" in classes and not self._content_depth:
            self._content_depth = 1
            self._parts = []
            return
        if self._content_depth:
            if tag == "div":
                self._content_depth += 1
            if tag in {"script", "style"}:
                self._skip_depth += 1
            if not self._skip_depth and tag in {"p", "div", "h1", "h2", "h3", "h4", "li", "tr"}:
                self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._content_depth and not self._skip_depth:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._content_depth:
            return
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
        if not self._skip_depth and tag in {"p", "div", "h1", "h2", "h3", "h4", "li", "tr"}:
            self._parts.append("\n")
        if tag == "div":
            self._content_depth -= 1
            if not self._content_depth:
                block = _clean_block("".join(self._parts))
                if block:
                    self.blocks.append(block)


class ShanghaiGGZYSource:
    """Experimental parser for Shanghai tender/prequalification pages.

    It is intentionally not registered as a production source until challenge
    detection and complete change/termination lifecycle handling are verified.
    """

    LIST_URL = _LIST_URL
    ENABLED_CHANNELS = {"2662": "招标公告/资格预审公告"}
    AUDIT_CHANNELS = ("2663", "2666")
    metadata = {
        "source_id": "shanghai-ggzy",
        "name": "上海市公共资源交易平台",
        "url": "https://www.shggzy.com/gqcg",
        "requires_login": False,
        "authority": 1.0,
        "production_ready": False,
    }

    def __init__(
        self,
        *,
        transport: HTTPTransport | None = None,
        timeout: float = 10,
        now: Any = None,
    ) -> None:
        self._transport = transport or _UrllibTransport()
        self._timeout = timeout
        self._now = now or (lambda: datetime.now(tz=SHANGHAI_TZ))

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
        fetched_at = self._now()
        if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
            raise ValueError("now() must return a timezone-aware datetime")
        fetched_at = fetched_at.astimezone(SHANGHAI_TZ)
        if task.regions and not any("上海" in region for region in task.regions):
            return []
        terms = _query_terms(task, plan)
        max_pages = max(1, min(int(plan.get("max_pages", 1)), 10))
        notices: list[TenderNotice] = []
        seen: set[str] = set()
        blocked_project_codes = await self._blocked_project_codes(
            task,
            audit_pages=max(3, max_pages),
        )

        for channel_id, channel_label in self.ENABLED_CHANNELS.items():
            for page in range(1, max_pages + 1):
                list_url = (
                    self.LIST_URL
                    if page == 1
                    else f"https://www.shggzy.com/search/queryContents_{page}.jhtml"
                )
                response = await self._request(
                    list_url,
                    params=self._list_params(task, channel_id),
                )
                parser = _ListParser()
                parser.feed(response.text)
                if not parser.found_list or channel_id not in parser.channel_ids:
                    raise ShanghaiGGZYStructureChangedError(
                        "Shanghai list category or result container changed"
                    )
                if not parser.items:
                    break
                for item in parser.items:
                    if not _is_shanghai_url(item.detail_url) or _has_conflict(item.title):
                        continue
                    if item.project_code and item.project_code in blocked_project_codes:
                        continue
                    matched_terms = _matched_terms(item.title, terms)
                    if terms and not matched_terms:
                        continue
                    if any(
                        exclusion.casefold() in item.title.casefold()
                        for exclusion in task.exclusions
                        if exclusion.strip()
                    ):
                        continue
                    if (
                        task.time_range_start is not None
                        and item.published_at < task.time_range_start
                    ) or (
                        task.time_range_end is not None
                        and item.published_at > task.time_range_end
                    ):
                        continue
                    detail = await self._request(item.detail_url, params=None)
                    notice = self._parse_notice(
                        item,
                        detail_html=detail.text,
                        channel_id=channel_id,
                        channel_label=channel_label,
                        matched_terms=matched_terms,
                        fetched_at=fetched_at,
                    )
                    if notice is None or notice.notice_stable_fingerprint in seen:
                        continue
                    seen.add(notice.notice_stable_fingerprint)
                    notices.append(notice)
        return notices

    async def _blocked_project_codes(
        self,
        task: TaskSpec,
        *,
        audit_pages: int,
    ) -> set[str]:
        """Quarantine originals with an unapplied change or abnormal event."""

        blocked: set[str] = set()
        for channel_id in self.AUDIT_CHANNELS:
            for page in range(1, min(audit_pages, 10) + 1):
                list_url = (
                    self.LIST_URL
                    if page == 1
                    else f"https://www.shggzy.com/search/queryContents_{page}.jhtml"
                )
                response = await self._request(
                    list_url,
                    params=self._list_params(task, channel_id),
                )
                parser = _ListParser()
                parser.feed(response.text)
                if not parser.found_list or channel_id not in parser.channel_ids:
                    raise ShanghaiGGZYStructureChangedError(
                        "Shanghai lifecycle audit category or container changed"
                    )
                blocked.update(
                    item.project_code
                    for item in parser.items
                    if item.project_code
                )
                if not parser.items:
                    break
        return blocked

    async def _request(
        self,
        url: str,
        *,
        params: dict[str, Any] | None,
    ) -> HTTPResponse:
        response = await self._transport.get(
            url,
            params=params,
            headers={
                "User-Agent": "BidRadar-X/1.0 (+local tender monitoring)",
                "Accept": "text/html,application/xhtml+xml",
                "Referer": "https://www.shggzy.com/gqcg",
            },
            timeout=self._timeout,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise ShanghaiGGZYSourceError(
                f"Shanghai platform returned HTTP {response.status_code}"
            )
        if not response.text.strip():
            raise ShanghaiGGZYStructureChangedError(
                "Shanghai platform returned an empty HTTP 200 response"
            )
        return response

    @staticmethod
    def _list_params(task: TaskSpec, channel_id: str) -> dict[str, str]:
        return {
            # Search by the user's confirmed subject at the source.  Previously
            # this was blank, so only the latest generic pages were inspected.
            "title": task.topic,
            "channelId": channel_id,
            "origin": "",
            "inDates": "",
            "timeBegin": (
                task.time_range_start.astimezone(SHANGHAI_TZ).date().isoformat()
                if task.time_range_start
                else ""
            ),
            "timeEnd": (
                task.time_range_end.astimezone(SHANGHAI_TZ).date().isoformat()
                if task.time_range_end
                else ""
            ),
            "ext": "",
            "ext1": "",
            "ext2": "",
            "ext3": "",
            "cExt": "1",
        }

    def _parse_notice(
        self,
        item: _ListItem,
        *,
        detail_html: str,
        channel_id: str,
        channel_label: str,
        matched_terms: list[str],
        fetched_at: datetime,
    ) -> TenderNotice | None:
        parser = _DetailParser()
        parser.feed(detail_html)
        if not parser.blocks:
            raise ShanghaiGGZYStructureChangedError(
                "Shanghai detail content container was not found"
            )
        body = max(parser.blocks, key=len)
        classification = _classify_and_extract_deadline(body)
        if classification is None:
            return None
        notice_type, deadline, deadline_quote, structure_quote = classification
        if deadline <= fetched_at or _title_contradicts(item.title, notice_type):
            return None
        region = "上海市"
        evidence = [
            EvidenceReference(
                evidence_id="evidence-notice-type",
                field_path="notice_type",
                source_url=item.detail_url,
                locator=f"channelId={channel_id}; 正文章节组合",
                quote=(
                    "生命周期归一为 tender；"
                    f"平台栏目：{channel_label}；{structure_quote}"
                ),
                fetched_at=fetched_at,
            ),
            EvidenceReference(
                evidence_id="evidence-opportunity-kind",
                field_path="opportunity_kind",
                source_url=item.detail_url,
                locator=f"channelId={channel_id}; 正文章节组合",
                quote=f"平台栏目：{channel_label}；{structure_quote}",
                fetched_at=fetched_at,
            ),
            EvidenceReference(
                evidence_id="evidence-deadline",
                field_path="deadline",
                source_url=item.detail_url,
                locator="对应递交章节内的截止时间字段",
                quote=deadline_quote,
                fetched_at=fetched_at,
            ),
            EvidenceReference(
                evidence_id="evidence-participation-status",
                field_path="participation_status",
                source_url=item.detail_url,
                locator="parsed deadline > fetched_at",
                quote=f"参与截止时间 {deadline:%Y-%m-%d %H:%M:%S} 晚于采集时间",
                fetched_at=fetched_at,
            ),
            EvidenceReference(
                evidence_id="evidence-region",
                field_path="region",
                source_url=item.detail_url,
                locator="上海市公共资源交易平台国企采购栏目",
                quote=region,
                fetched_at=fetched_at,
            ),
        ]
        if item.project_code:
            evidence.append(
                EvidenceReference(
                    evidence_id="evidence-project-code",
                    field_path="project_code",
                    source_url=item.detail_url,
                    locator="公告列表：项目编号",
                    quote=item.project_code,
                    fetched_at=fetched_at,
                )
            )
        if matched_terms:
            evidence.append(
                EvidenceReference(
                    evidence_id="evidence-topic-keywords",
                    field_path="topic_keywords",
                    source_url=item.detail_url,
                    locator="公告列表：名称",
                    quote=item.title,
                    fetched_at=fetched_at,
                )
            )
        source_notice_id = urlparse(item.detail_url).path.rstrip("/").rsplit("/", 1)[-1]
        project_title = re.sub(
            r"(?:资格预审|招标|公告|公示|第.+?次)", "", item.title
        )
        return TenderNotice(
            notice_id=f"shggzy-{source_notice_id}",
            notice_type="tender",
            opportunity_kind=notice_type,
            project_code=item.project_code,
            title=item.title,
            published_at=item.published_at,
            source=SourceRecord(
                source_id=self.metadata["source_id"],
                source_name=self.metadata["name"],
                source_url=item.detail_url,
                publication_role="original",
                source_notice_id=source_notice_id,
                authority=self.metadata["authority"],
            ),
            core_content=body[:100_000],
            region=region,
            topic_keywords=matched_terms,
            deadline=deadline,
            raw_content_fingerprint=_sha256(detail_html),
            notice_stable_fingerprint=_sha256(
                f"{notice_type}|{item.project_code or ''}|{item.title}|{item.published_at.date()}"
            ),
            project_stable_fingerprint=(
                _sha256(item.project_code)
                if item.project_code
                else _sha256(_identity(project_title or item.title))
            ),
            fetched_at=fetched_at,
            evidence=evidence,
        )


def _classify_and_extract_deadline(
    body: str,
) -> tuple[str, datetime, str, str] | None:
    compact = re.sub(r"[ \t\r\f\v]+", "", body)
    pre_get = any(
        marker in compact for marker in ("资格预审文件的获取", "资格预审文件获取")
    )
    pre_submit = any(
        marker in compact
        for marker in (
            "资格预审申请文件的递交",
            "资格预审申请文件递交",
            "申请文件的递交",
        )
    )
    tender_get = any(
        marker in compact for marker in ("招标文件的获取", "招标文件获取")
    )
    tender_submit = any(
        marker in compact
        for marker in ("投标文件的递交", "投标文件递交", "投标文件递交截止")
    )
    is_prequalification = pre_get and pre_submit
    is_tender = tender_get and tender_submit
    if is_prequalification == is_tender:
        return None
    if is_prequalification:
        notice_type = "prequalification"
        anchors = ("资格预审申请文件的递交", "资格预审申请文件递交", "申请文件的递交")
        structure_quote = "正文同时包含资格预审文件获取与申请文件递交章节"
    else:
        notice_type = "tender"
        anchors = ("投标文件的递交", "投标文件递交")
        structure_quote = "正文同时包含招标文件获取与投标文件递交章节"
    start = min(
        (compact.find(anchor) for anchor in anchors if compact.find(anchor) >= 0),
        default=-1,
    )
    if start < 0:
        return None
    deadline = _extract_labeled_deadline(compact[start : start + 1600])
    if deadline is None:
        return None
    parsed, quote = deadline
    return notice_type, parsed, quote, structure_quote


def _extract_labeled_deadline(text: str) -> tuple[datetime, str] | None:
    label = r"(?:递交截止时间|申请文件递交截止时间|投标截止时间)\s*[：:]?\s*"
    chinese = re.search(
        label
        + r"(?P<quote>(?P<y>20\d{2})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日"
        r"(?:上午|下午)?(?P<h>\d{1,2})[：:时](?P<minute>\d{1,2})(?:分)?)",
        text,
    )
    if chinese:
        hour = int(chinese.group("h"))
        prefix = chinese.group(0)
        if "下午" in prefix and hour < 12:
            hour += 12
        try:
            parsed = datetime(
                int(chinese.group("y")),
                int(chinese.group("m")),
                int(chinese.group("d")),
                hour,
                int(chinese.group("minute")),
                tzinfo=SHANGHAI_TZ,
            )
        except ValueError:
            return None
        return parsed, chinese.group(0)
    western = re.search(
        label
        + r"(?P<quote>(?P<y>20\d{2})[-/](?P<m>\d{1,2})[-/](?P<d>\d{1,2})"
        r"\s+(?P<h>\d{1,2})[：:](?P<minute>\d{1,2}))",
        text,
    )
    if western:
        try:
            parsed = datetime(
                int(western.group("y")),
                int(western.group("m")),
                int(western.group("d")),
                int(western.group("h")),
                int(western.group("minute")),
                tzinfo=SHANGHAI_TZ,
            )
        except ValueError:
            return None
        return parsed, western.group(0)
    return None


def _onclick_path(value: str) -> str | None:
    match = re.search(r"window\.open\(['\"]([^'\"]+)['\"]", value)
    return match.group(1).strip() if match else None


def _parse_date(value: str) -> datetime | None:
    match = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", value)
    if not match:
        return None
    try:
        return datetime(*(int(part) for part in match.groups()), tzinfo=SHANGHAI_TZ)
    except ValueError:
        return None


def _query_terms(task: TaskSpec, plan: Mapping[str, Any]) -> list[str]:
    values = [str(plan.get("query") or ""), *task.keywords, task.topic]
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _matched_terms(title: str, terms: list[str]) -> list[str]:
    folded = title.casefold()
    return [term for term in terms if term.casefold() in folded]


def _has_conflict(title: str) -> bool:
    return any(marker in title for marker in _CONFLICTS)


def _title_contradicts(title: str, notice_type: str) -> bool:
    if notice_type == "prequalification" and "招标公告" in title and "资格预审" not in title:
        return True
    if notice_type == "tender" and ("资格预审" in title or "资审公告" in title):
        return True
    return _has_conflict(title)


def _is_shanghai_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and (
        host == "shggzy.com" or host.endswith(".shggzy.com")
    )


def _clean_inline(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().replace("\xa0", " ").strip()


def _clean_block(value: str) -> str:
    lines = [_clean_inline(line) for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def _identity(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "HTTPResponse",
    "ShanghaiGGZYSource",
    "ShanghaiGGZYSourceError",
    "ShanghaiGGZYStructureChangedError",
]
