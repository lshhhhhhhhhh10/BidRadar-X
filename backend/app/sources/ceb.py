"""China Tendering and Bidding Public Service Platform adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import re
from typing import Any, Mapping, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from app.schemas.tender import (
    EvidenceReference,
    SourceRecord,
    TaskSpec,
    TenderNotice,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_SPACE_RE = re.compile(r"\s+")
_OPENING_CONFLICTS = (
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
)
class CEBSourceError(RuntimeError):
    """Raised when the national platform cannot be collected safely."""


class CEBStructureChangedError(CEBSourceError):
    """Raised when the official list no longer exposes the expected table."""


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
        params: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> HTTPResponse:
        ...


class _UrllibTransport:
    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any],
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
        params: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> HTTPResponse:
        request_url = f"{url}?{urlencode(params)}"
        request = Request(request_url, headers=headers, method="GET")
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read(10_000_001)
            if len(body) > 10_000_000:
                raise CEBSourceError("national platform response exceeded 10 MB")
            charset = response.headers.get_content_charset() or "utf-8"
            return HTTPResponse(
                url=response.geturl(),
                text=body.decode(charset, errors="replace"),
                status_code=response.status,
            )


@dataclass(frozen=True)
class _ListItem:
    title: str
    notice_uuid: str
    industry: str | None
    region: str | None
    channel: str | None
    published_at: datetime
    open_time: datetime


class _ListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found_table = False
        self.items: list[_ListItem] = []
        self._table_depth = 0
        self._in_row = False
        self._cells: list[str] = []
        self._cell_parts: list[str] | None = None
        self._cell_titles: list[str] = []
        self._row_cell_titles: list[list[str]] = []
        self._notice_title: str | None = None
        self._notice_uuid: str | None = None
        self._open_time: datetime | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "table" and "table_text" in classes and not self._table_depth:
            self.found_table = True
            self._table_depth = 1
            return
        if self._table_depth:
            if tag == "table":
                self._table_depth += 1
            if tag == "tr":
                self._in_row = True
                self._cells = []
                self._row_cell_titles = []
                self._notice_title = None
                self._notice_uuid = None
                self._open_time = None
            elif self._in_row and tag in {"td", "th"}:
                self._cell_parts = []
                self._cell_titles = []
                if attributes.get("name") == "openTime":
                    self._open_time = _parse_datetime(attributes.get("id"))
            elif self._cell_parts is not None:
                title = attributes.get("title")
                if title:
                    self._cell_titles.append(_clean(title))
                if tag == "a":
                    self._notice_title = _clean(title or "") or self._notice_title
                    self._notice_uuid = _javascript_uuid(attributes.get("href") or "")

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._cell_parts is not None and tag in {"td", "th"}:
            self._cells.append(_clean(" ".join(self._cell_parts)))
            self._row_cell_titles.append(self._cell_titles)
            self._cell_parts = None
            self._cell_titles = []
        if self._table_depth and tag == "tr" and self._in_row:
            self._finish_row()
            self._in_row = False
        if self._table_depth and tag == "table":
            self._table_depth -= 1

    def _finish_row(self) -> None:
        if (
            not self._notice_title
            or not self._notice_uuid
            or self._open_time is None
            or len(self._cells) < 6
        ):
            return
        published = _parse_date(self._cells[-2])
        if published is None:
            return
        region_titles = self._row_cell_titles[2] if len(self._row_cell_titles) > 2 else []
        self.items.append(
            _ListItem(
                title=self._notice_title,
                notice_uuid=self._notice_uuid,
                industry=self._cells[1] or None,
                region=(region_titles[0] if region_titles else self._cells[2]) or None,
                channel=self._cells[3] or None,
                published_at=published,
                open_time=self._open_time,
            )
        )


class _CorrectionAuditParser(HTMLParser):
    """Read category 89 to quarantine originals with unapplied later events."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found_table = False
        self.found_rows = False
        self.affected_notice_ids: set[str] = set()
        self._table_depth = 0
        self._in_row = False
        self._row_links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "table" and "table_text" in classes and not self._table_depth:
            self.found_table = True
            self._table_depth = 1
            return
        if not self._table_depth:
            return
        if tag == "table":
            self._table_depth += 1
        if tag == "tr":
            self._in_row = True
            self._row_links = []
        elif self._in_row and tag == "a":
            notice_uuid = _javascript_uuid(attributes.get("href") or "")
            title = _clean(attributes.get("title") or "")
            if notice_uuid:
                self._row_links.append((notice_uuid, title))

    def handle_endtag(self, tag: str) -> None:
        if self._in_row and tag == "tr":
            if self._row_links:
                self.found_rows = True
                # Until the correction body and revised deadline can be
                # verified, any later category-89 event quarantines the
                # associated original instead of leaving stale data visible.
                self.affected_notice_ids.update(
                    notice_uuid for notice_uuid, _ in self._row_links
                )
            self._in_row = False
        if self._table_depth and tag == "table":
            self._table_depth -= 1


class CEBSource:
    """Experimental parser for source-classified CEB list pages.

    It is intentionally not registered as a production source until challenge
    detection, content-type validation and correction lifecycle handling meet
    the documented source contract.
    """

    CATEGORY_URLS = {
        "prequalification": (
            "https://bulletin.cebpubservice.com/xxfbcmses/search/qualify.html"
        ),
        "tender": (
            "https://bulletin.cebpubservice.com/xxfbcmses/search/bulletin.html"
        ),
    }
    CATEGORY_IDS = {
        "prequalification": "92",
        "tender": "88",
    }
    CATEGORY_LABELS = {
        "prequalification": "资格预审公告",
        "tender": "招标公告",
    }
    CORRECTION_AUDIT_URL = (
        "https://bulletin.cebpubservice.com/xxfbcmses/search/change.html"
    )
    USER_AGENT = "BidRadar-X/1.0 (+local tender monitoring)"
    metadata = {
        "source_id": "ceb-public-service",
        "name": "中国招标投标公共服务平台",
        "url": "https://bulletin.cebpubservice.com/",
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
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now() must return a timezone-aware datetime")
        now = now.astimezone(SHANGHAI_TZ)
        terms = _query_terms(task, plan)
        max_pages = max(1, min(int(plan.get("max_pages", 1)), 10))
        notices: list[TenderNotice] = []
        seen: set[str] = set()
        affected_notice_ids = await self._affected_notice_ids(
            audit_pages=max(3, max_pages)
        )

        for notice_type, url in self.CATEGORY_URLS.items():
            for page in range(1, max_pages + 1):
                params = {
                    # Let the official platform do the first-stage recall instead
                    # of scanning only the newest unfiltered pages.  Publication
                    # dates are filtered locally when the user actually supplies
                    # a time range; an empty value means "no publication limit".
                    "dates": "",
                    "word": task.topic,
                    "categoryId": self.CATEGORY_IDS[notice_type],
                    "industryName": "",
                    "area": "",
                    "status": "01",
                    "publishMedia": "",
                    "sourceInfo": "",
                    "showStatus": "1",
                    "signDate": f"{now:%Y-%m-%d %H:%M:%S},lt",
                    "page": str(page),
                }
                response = await self._transport.get(
                    url,
                    params=params,
                    headers={"User-Agent": self.USER_AGENT, "Accept": "text/html"},
                    timeout=self._timeout,
                )
                if response.status_code < 200 or response.status_code >= 300:
                    raise CEBSourceError(
                        f"national platform returned HTTP {response.status_code}"
                    )
                parser = _ListingParser()
                parser.feed(response.text)
                if not parser.found_table:
                    raise CEBStructureChangedError(
                        "national platform list table was not found"
                    )
                if not parser.items:
                    break
                for item in parser.items:
                    if item.notice_uuid in affected_notice_ids:
                        continue
                    if _has_conflict(item.title):
                        continue
                    if not _title_matches_native_category(notice_type, item.title):
                        continue
                    if item.open_time <= now:
                        continue
                    if (
                        task.time_range_start is not None
                        and item.published_at < task.time_range_start
                    ) or (
                        task.time_range_end is not None
                        and item.published_at > task.time_range_end
                    ):
                        continue
                    if task.regions and not any(
                        requested.casefold() in (item.region or "").casefold()
                        or (item.region or "").casefold() in requested.casefold()
                        for requested in task.regions
                    ):
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
                    identity = _sha256(
                        f"{notice_type}|{item.title}|{item.published_at.date()}"
                    )
                    if identity in seen:
                        continue
                    seen.add(identity)
                    notices.append(
                        self._to_notice(
                            item,
                            notice_type=notice_type,
                            list_url=response.url,
                            matched_terms=matched_terms,
                            fetched_at=now,
                        )
                    )
        return notices

    async def _affected_notice_ids(
        self,
        *,
        audit_pages: int,
    ) -> set[str]:
        affected_ids: set[str] = set()
        for page in range(1, min(audit_pages, 10) + 1):
            params = {
                "dates": "90",
                "word": "",
                "categoryId": "89",
                "industryName": "",
                "area": "",
                "status": "",
                "publishMedia": "",
                "sourceInfo": "",
                "showStatus": "1",
                "page": str(page),
            }
            response = await self._transport.get(
                self.CORRECTION_AUDIT_URL,
                params=params,
                headers={"User-Agent": self.USER_AGENT, "Accept": "text/html"},
                timeout=self._timeout,
            )
            if response.status_code < 200 or response.status_code >= 300:
                raise CEBSourceError(
                    f"national correction audit returned HTTP {response.status_code}"
                )
            parser = _CorrectionAuditParser()
            parser.feed(response.text)
            if not parser.found_table:
                raise CEBStructureChangedError(
                    "national correction audit table was not found"
                )
            affected_ids.update(parser.affected_notice_ids)
            if not parser.found_rows:
                break
        return affected_ids

    def _to_notice(
        self,
        item: _ListItem,
        *,
        notice_type: str,
        list_url: str,
        matched_terms: list[str],
        fetched_at: datetime,
    ) -> TenderNotice:
        category_label = self.CATEGORY_LABELS[notice_type]
        evidence = [
            EvidenceReference(
                evidence_id="evidence-notice-type",
                field_path="notice_type",
                source_url=list_url,
                locator=f"categoryId={self.CATEGORY_IDS[notice_type]}",
                quote=(
                    f"生命周期归一为 tender；平台原生机会类别：{category_label}"
                ),
                fetched_at=fetched_at,
            ),
            EvidenceReference(
                evidence_id="evidence-opportunity-kind",
                field_path="opportunity_kind",
                source_url=list_url,
                locator=f"categoryId={self.CATEGORY_IDS[notice_type]}",
                quote=f"平台原生栏目：{category_label}",
                fetched_at=fetched_at,
            ),
            EvidenceReference(
                evidence_id="evidence-participation-status",
                field_path="participation_status",
                source_url=list_url,
                locator=f"tr(uuid={item.notice_uuid}) openTime > fetched_at",
                quote="平台 openTime 晚于采集时间",
                fetched_at=fetched_at,
            ),
        ]
        if item.region:
            evidence.append(
                EvidenceReference(
                    evidence_id="evidence-region",
                    field_path="region",
                    source_url=list_url,
                    locator="公告列表：所属地区",
                    quote=item.region,
                    fetched_at=fetched_at,
                )
            )
        if matched_terms:
            evidence.append(
                EvidenceReference(
                    evidence_id="evidence-topic-keywords",
                    field_path="topic_keywords",
                    source_url=list_url,
                    locator="公告列表：公告名称",
                    quote=item.title,
                    fetched_at=fetched_at,
                )
            )
        content = "\n".join(
            value
            for value in (
                f"公告阶段：{category_label}",
                f"公告名称：{item.title}",
                f"所属行业：{item.industry}" if item.industry else "",
                f"所属地区：{item.region}" if item.region else "",
                f"来源渠道：{item.channel}" if item.channel else "",
                f"参与截止时间：{item.open_time:%Y-%m-%d %H:%M:%S}",
                "有效状态：平台 openTime 晚于采集时间",
            )
            if value
        )
        project_title = re.sub(
            r"(?:资格预审|招标|更正|变更|公告|公示|补充|第.+?次)",
            "",
            item.title,
        )
        canonical_url = (
            "https://ctbpsp.com/#/bulletinDetail?"
            f"uuid={item.notice_uuid}&inpvalue=&dataSource=0&tenderAgency="
        )
        evidence.append(
            EvidenceReference(
                evidence_id="evidence-deadline",
                field_path="deadline",
                source_url=list_url,
                locator=f"tr(uuid={item.notice_uuid}) td[name=openTime]@id",
                quote=f"openTime={item.open_time:%Y-%m-%d %H:%M:%S}",
                fetched_at=fetched_at,
            )
        )
        return TenderNotice(
            notice_id=f"ceb-{_sha256(f'{notice_type}|{item.title}|{item.published_at}')[:24]}",
            notice_type="tender",
            opportunity_kind=notice_type,
            title=item.title,
            published_at=item.published_at,
            source=SourceRecord(
                source_id=self.metadata["source_id"],
                source_name=self.metadata["name"],
                source_url=canonical_url,
                publication_role="republication",
                canonical_notice_url=None,
                source_notice_id=item.notice_uuid,
                authority=self.metadata["authority"],
            ),
            core_content=content,
            region=item.region,
            topic_keywords=matched_terms,
            deadline=item.open_time,
            raw_content_fingerprint=_sha256(content),
            notice_stable_fingerprint=_sha256(
                f"{notice_type}|{item.title}|{item.published_at.date()}"
            ),
            project_stable_fingerprint=_sha256(_identity(project_title or item.title)),
            fetched_at=fetched_at,
            evidence=evidence,
        )


def _query_terms(task: TaskSpec, plan: Mapping[str, Any]) -> list[str]:
    values = [str(plan.get("query") or ""), *task.keywords, task.topic]
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _matched_terms(title: str, terms: list[str]) -> list[str]:
    folded = title.casefold()
    return [term for term in terms if term.casefold() in folded]


def _has_conflict(title: str) -> bool:
    return any(marker in title for marker in _OPENING_CONFLICTS)


def _javascript_uuid(value: str) -> str | None:
    match = re.search(r"urlOpen\(['\"]([^'\"]+)['\"]\)", value)
    if not match:
        return None
    candidate = match.group(1).strip()
    return candidate if re.fullmatch(r"[0-9A-Za-z_-]{6,80}", candidate) else None


def _parse_date(value: str) -> datetime | None:
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
    if not match:
        return None
    try:
        return datetime(*(int(part) for part in match.groups()), tzinfo=SHANGHAI_TZ)
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=SHANGHAI_TZ
        )
    except ValueError:
        return None


def _title_matches_native_category(notice_type: str, title: str) -> bool:
    if notice_type == "prequalification":
        return "资格预审" in title or "资审公告" in title
    if notice_type == "tender":
        return "招标公告" in title or "公开招标" in title
    return False


def _identity(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def _clean(value: str) -> str:
    return _SPACE_RE.sub(" ", value).strip()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "CEBSource",
    "CEBSourceError",
    "CEBStructureChangedError",
    "HTTPResponse",
]
