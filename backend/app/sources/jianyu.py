"""Safe, offline experiment for the login-gated Jianyu tender source.

The public Jianyu licence prohibits unapproved third-party systems from logging
in or copying service interaction data.  This module therefore deliberately
does not perform network navigation.  It provides the bounded pieces needed to
validate an authorised experiment later: an external Playwright storage-state
loader, login-wall detection, and deterministic HTML parsers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urljoin, urlparse


SESSION_STATE_ENV = "BIDRADAR_JIANYU_STORAGE_STATE_FILE"
_ALLOWED_HOST = "jianyu360.cn"
_MAX_STORAGE_STATE_BYTES = 2 * 1024 * 1024
_MAX_HTML_BYTES = 5 * 1024 * 1024
_CHINA_TZ = timezone(timedelta(hours=8))


class JianyuSourceError(RuntimeError):
    """Base error for this experimental source."""


class JianyuSessionError(JianyuSourceError):
    """The external browser session is absent or unsafe to load."""


class JianyuAuthenticationError(JianyuSourceError):
    """The supplied page is not accessible to the authenticated member."""


class JianyuParsingError(JianyuSourceError):
    """The page does not contain the minimum required notice fields."""


class JianyuAutomationNotAuthorizedError(JianyuSourceError):
    """Live browser collection is disabled without written site permission."""


@dataclass(frozen=True)
class JianyuLoginSession:
    """A validated reference to a Playwright state file outside the repository.

    The secret-bearing JSON is intentionally not retained on this object.  A
    caller with explicit authorisation may pass ``storage_state_path`` directly
    to ``browser.new_context(storage_state=...)``.
    """

    storage_state_path: Path

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        *,
        repository_root: Path | None = None,
    ) -> JianyuLoginSession:
        values = os.environ if environment is None else environment
        configured = values.get(SESSION_STATE_ENV, "").strip()
        if not configured:
            raise JianyuSessionError(
                f"missing {SESSION_STATE_ENV}; no authenticated session is configured"
            )
        if configured.startswith(("{", "[")):
            raise JianyuSessionError(
                f"{SESSION_STATE_ENV} must reference an external file, not inline JSON"
            )

        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            raise JianyuSessionError(
                f"{SESSION_STATE_ENV} must be an absolute path outside the repository"
            )
        if candidate.is_symlink():
            raise JianyuSessionError("the configured storage-state file must not be a symlink")

        resolved = candidate.resolve(strict=False)
        root = (
            repository_root.resolve()
            if repository_root is not None
            else Path(__file__).resolve().parents[3]
        )
        if _is_relative_to(resolved, root):
            raise JianyuSessionError("the storage-state file must be kept outside the repository")
        if not resolved.is_file():
            raise JianyuSessionError("the configured storage-state file does not exist")
        if resolved.stat().st_size > _MAX_STORAGE_STATE_BYTES:
            raise JianyuSessionError("the configured storage-state file is unexpectedly large")

        try:
            state = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise JianyuSessionError("the configured storage-state file is not valid JSON") from error
        _validate_storage_state(state)
        return cls(storage_state_path=resolved)


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    children: list[_Node] = field(default_factory=list)
    content: list[Any] = field(default_factory=list)

    @property
    def text(self) -> str:
        values = [item.text if isinstance(item, _Node) else item for item in self.content]
        return _clean_text("".join(values))


class _TreeBuilder(HTMLParser):
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
        self.root = _Node("document", {})
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag.lower(), {name.lower(): value or "" for name, value in attrs})
        self._stack[-1].children.append(node)
        self._stack[-1].content.append(node)
        if node.tag not in self._VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._stack[-1].tag == tag.lower() and tag.lower() not in self._VOID_TAGS:
            self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == lowered:
                del self._stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._stack[-1].content.append(data)


class JianyuSource:
    """Parser-only Jianyu experiment; it is intentionally not workflow-wired."""

    metadata = {
        "source_id": "jianyu-experiment",
        "name": "剑鱼标讯（授权前离线实验）",
        "requires_login": True,
        "session_status": "external_session_required",
        "live_collection": "disabled_pending_written_authorization",
    }

    def __init__(self, session: JianyuLoginSession | None = None) -> None:
        self.session = session

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        *,
        repository_root: Path | None = None,
    ) -> JianyuSource:
        return cls(
            JianyuLoginSession.from_environment(
                environment,
                repository_root=repository_root,
            )
        )

    async def collect(
        self,
        task_spec: dict[str, Any],
        search_plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        del task_spec, search_plan
        if self.session is None:
            raise JianyuSessionError(
                f"missing {SESSION_STATE_ENV}; no authenticated session is configured"
            )
        raise JianyuAutomationNotAuthorizedError(
            "live Jianyu automation is disabled: obtain written platform authorisation "
            "or use its official developer API"
        )

    @staticmethod
    def parse_notice_list(
        html: str,
        *,
        base_url: str = "https://www.jianyu360.cn/",
    ) -> list[dict[str, Any]]:
        _assert_authorized_page(html, base_url)
        root = _parse_html(html)
        candidates = [
            node
            for node in _walk(root)
            if node.tag in {"article", "li", "div"}
            and (
                "data-notice-id" in node.attrs
                or _classes(node).intersection(
                    {"notice-item", "search-item", "search-list-item", "list-item"}
                )
            )
        ]

        records: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for candidate in candidates:
            link = _first(
                candidate,
                lambda node: node.tag == "a"
                and bool(node.attrs.get("href"))
                and (
                    "/jybx/" in node.attrs["href"]
                    or bool(_classes(node).intersection({"notice-title", "title", "notice-link"}))
                ),
            )
            if link is None or not link.text:
                continue
            url = _safe_jianyu_url(link.attrs["href"], base_url)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            published_text = _first_text_by_class(
                candidate,
                {"publish-time", "published-at", "date", "time"},
            ) or _match_group(candidate.text, r"(?:发布日期|发布时间)\s*[:：]?\s*([^|]+)")
            region = _first_text_by_class(candidate, {"region", "area", "province"})
            source_notice_id = candidate.attrs.get("data-notice-id") or Path(
                urlparse(url).path
            ).stem
            records.append(
                {
                    "source_notice_id": source_notice_id,
                    "title": link.text,
                    "url": url,
                    "published_at": _parse_datetime(published_text) if published_text else None,
                    "region": region,
                }
            )

        if not records:
            raise JianyuParsingError("no notice records were found in the authenticated list page")
        return records

    @staticmethod
    def parse_notice_detail(html: str, *, url: str) -> dict[str, Any]:
        _assert_authorized_page(html, url)
        safe_url = _safe_jianyu_url(url, url)
        root = _parse_html(html)

        title_node = _first(
            root,
            lambda node: node.tag == "h1"
            or bool(_classes(node).intersection({"notice-title", "detail-title"})),
        )
        content_node = _first(
            root,
            lambda node: bool(
                _classes(node).intersection(
                    {"notice-content", "detail-content", "article-content", "content-body"}
                )
            ),
        )
        if title_node is None or not title_node.text:
            raise JianyuParsingError("the detail page is missing its notice title")
        if content_node is None or not content_node.text:
            raise JianyuParsingError("the detail page is missing its notice body")

        labelled = _labelled_values(root)
        page_text = root.text
        published_text = _value_for(labelled, "发布日期", "发布时间", "公告开始时间")
        if not published_text:
            published_text = _match_group(
                page_text,
                r"(?:发布日期|发布时间)\s*[:：]?\s*(\d{4}[-年/]\d{1,2}[-月/]\d{1,2}(?:[日\s]+\d{1,2}:\d{2}(?::\d{2})?)?)",
            )
        published_at = _parse_datetime(published_text) if published_text else None
        if published_at is None:
            raise JianyuParsingError("the detail page is missing a parseable publication time")

        attachments: list[dict[str, str]] = []
        for node in _walk(root):
            if node.tag != "a" or not node.attrs.get("href"):
                continue
            href = node.attrs["href"]
            if not re.search(r"\.(?:pdf|docx?|xlsx?|zip|rar)(?:$|[?#])", href, re.IGNORECASE):
                continue
            attachment_url = urljoin(safe_url, href)
            parsed_attachment = urlparse(attachment_url)
            if (
                parsed_attachment.scheme not in {"http", "https"}
                or not parsed_attachment.netloc
                or parsed_attachment.username is not None
                or parsed_attachment.password is not None
            ):
                continue
            attachments.append({"name": node.text or Path(parsed_attachment.path).name, "url": attachment_url})

        budget_text = _value_for(labelled, "预算金额", "项目预算", "最高限价")
        deadline_text = _value_for(
            labelled,
            "投标截止时间",
            "文件递交截止时间",
            "公告截止时间",
            "开标时间",
        )
        region = _value_for(labelled, "地区", "所属地区", "省份")
        purchaser = _value_for(labelled, "采购单位", "招标人", "采购人")
        project_code = _value_for(labelled, "项目编号", "招标编号", "采购项目编号")

        return {
            "source_id": JianyuSource.metadata["source_id"],
            "source_name": "剑鱼标讯",
            "source_notice_id": Path(urlparse(safe_url).path).stem,
            "url": safe_url,
            "title": title_node.text,
            "published_at": published_at,
            "document_type": "html",
            "notice_type": _notice_type(title_node.text),
            "project_code": project_code,
            "purchaser": purchaser,
            "budget": _parse_budget(budget_text) if budget_text else None,
            "deadline": _parse_datetime(deadline_text) if deadline_text else None,
            "region": region,
            "content": content_node.text,
            "attachments": attachments,
        }


def _validate_storage_state(state: Any) -> None:
    if not isinstance(state, dict):
        raise JianyuSessionError("the storage-state JSON must be an object")
    cookies = state.get("cookies")
    origins = state.get("origins")
    if not isinstance(cookies, list) or not isinstance(origins, list):
        raise JianyuSessionError("the storage-state JSON is not in Playwright format")

    has_auth_material = False
    for cookie in cookies:
        if not isinstance(cookie, dict):
            raise JianyuSessionError("the storage-state cookies are malformed")
        domain = str(cookie.get("domain", "")).lstrip(".").lower()
        if domain and not _is_allowed_host(domain):
            raise JianyuSessionError("the storage state contains a cookie for an unexpected domain")
        if domain and cookie.get("name") and cookie.get("value"):
            has_auth_material = True

    for origin in origins:
        if not isinstance(origin, dict):
            raise JianyuSessionError("the storage-state origins are malformed")
        raw_origin = str(origin.get("origin", ""))
        parsed = urlparse(raw_origin)
        if parsed.scheme != "https" or not _is_allowed_host(parsed.hostname or ""):
            raise JianyuSessionError("the storage state contains an unexpected origin")
        local_storage = origin.get("localStorage", [])
        if not isinstance(local_storage, list):
            raise JianyuSessionError("the storage-state localStorage entry is malformed")
        if local_storage:
            has_auth_material = True

    if not has_auth_material:
        raise JianyuSessionError("the storage state contains no authentication material")


def _assert_authorized_page(html: str, url: str) -> None:
    _safe_jianyu_url(url, url)
    if len(html.encode("utf-8")) > _MAX_HTML_BYTES:
        raise JianyuParsingError("the HTML page exceeds the parser size limit")
    normalized = _clean_text(re.sub(r"<[^>]+>", " ", html))
    barriers = (
        "登录后即可免费查看完整信息",
        "当前页面需要登录后查看",
        "会话已失效，请重新登录",
    )
    if any(marker in normalized for marker in barriers):
        raise JianyuAuthenticationError(
            "the Jianyu session is missing or expired; the page is still login-gated"
        )


def _parse_html(html: str) -> _Node:
    parser = _TreeBuilder()
    parser.feed(html)
    parser.close()
    return parser.root


def _walk(node: _Node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _first(node: _Node, predicate) -> _Node | None:
    return next((candidate for candidate in _walk(node) if predicate(candidate)), None)


def _classes(node: _Node) -> set[str]:
    return {value.lower() for value in node.attrs.get("class", "").split() if value}


def _first_text_by_class(node: _Node, class_names: set[str]) -> str | None:
    found = _first(node, lambda candidate: bool(_classes(candidate).intersection(class_names)))
    return found.text if found is not None and found.text else None


def _labelled_values(root: _Node) -> dict[str, str]:
    values: dict[str, str] = {}
    for row in (node for node in _walk(root) if node.tag == "tr"):
        cells = [child.text for child in row.children if child.tag in {"th", "td"} and child.text]
        for index in range(0, len(cells) - 1, 2):
            values.setdefault(_normalize_label(cells[index]), cells[index + 1])
    for node in _walk(root):
        label = node.attrs.get("data-label")
        value = node.attrs.get("data-value")
        if label and value:
            values.setdefault(_normalize_label(label), _clean_text(value))
    return values


def _value_for(values: Mapping[str, str], *labels: str) -> str | None:
    for label in labels:
        value = values.get(_normalize_label(label))
        if value:
            return value
    return None


def _normalize_label(value: str) -> str:
    return re.sub(r"[\s:：]", "", value)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _match_group(value: str, pattern: str) -> str | None:
    match = re.search(pattern, value, re.IGNORECASE)
    return _clean_text(match.group(1)) if match else None


def _parse_datetime(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _clean_text(value).replace("年", "-").replace("月", "-").replace("日", " ")
    normalized = normalized.replace("/", "-")
    match = re.search(r"(\d{4}-\d{1,2}-\d{1,2})(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?", normalized)
    if not match:
        return None
    time_part = match.group(2) or "00:00:00"
    if time_part.count(":") == 1:
        time_part += ":00"
    parsed = datetime.strptime(f"{match.group(1)} {time_part}", "%Y-%m-%d %H:%M:%S")
    return parsed.replace(tzinfo=_CHINA_TZ).isoformat()


def _parse_budget(value: str) -> str | None:
    match = re.search(r"([\d,]+(?:\.\d+)?)\s*(万)?\s*元?", value.replace("￥", ""))
    if not match:
        return None
    try:
        amount = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None
    if match.group(2):
        amount *= Decimal("10000")
    return format(amount, "f")


def _notice_type(title: str) -> str:
    if "更正" in title or "变更" in title or "延期" in title:
        return "correction"
    if "中标" in title or "成交" in title or "结果" in title:
        return "award"
    if "终止" in title or "废标" in title or "取消" in title:
        return "cancellation"
    if "招标" in title or "采购" in title or "询价" in title:
        return "tender"
    return "other"


def _safe_jianyu_url(value: str, base_url: str) -> str:
    absolute = urljoin(base_url, value)
    parsed = urlparse(absolute)
    if (
        parsed.scheme != "https"
        or not _is_allowed_host(parsed.hostname or "")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
    ):
        raise JianyuParsingError("only HTTPS Jianyu URLs are accepted")
    return absolute


def _is_allowed_host(host: str) -> bool:
    lowered = host.lower().rstrip(".")
    return lowered == _ALLOWED_HOST or lowered.endswith(f".{_ALLOWED_HOST}")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
