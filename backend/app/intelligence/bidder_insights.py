from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import re
from typing import Any, Sequence

from ..schemas.tender import TenderNotice
from .text_sanitizer import sanitize_notice_text


_FIELD_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("qualification", "资格与资质要求", ("申请人的资格要求", "投标人资格", "供应商资格", "资格条件", "资质要求")),
    ("bond", "投标保证金", ("投标保证金", "响应保证金", "保证金金额")),
    ("duration", "工期 / 服务期", ("合同履行期限", "服务期限", "服务期", "计划工期", "工期", "交付期限")),
    ("evaluation", "评审办法", ("评标办法", "评审方法", "综合评分法", "最低评标价法", "评标方法")),
    ("location", "递交 / 开标地点", ("开标地点", "投标文件递交地点", "响应文件提交地点", "递交地点")),
    ("payment", "付款与结算", ("付款方式", "支付方式", "结算方式", "付款条件")),
)

_PHONE = re.compile(r"(?<!\d)(?:1[3-9]\d{9}|0\d{2,3}[\s-]?\d{7,8}(?:[\s-]\d{1,6})?)(?!\d)")
_CONTACT = re.compile(
    r"(?P<role>项目联系人|采购人联系人|招标人联系人|代理机构联系人|采购代理联系人|联系人)"
    r"\s*[：:]?\s*(?P<name>[\u4e00-\u9fff·]{2,8})?",
)


def build_bidder_insights(notices: Sequence[TenderNotice]) -> dict[str, list[dict[str, Any]]]:
    if not notices:
        return {"items": [], "contacts": []}
    primary = max(
        notices,
        key=lambda notice: (
            notice.source.authority or 0,
            notice.published_at,
            len(notice.core_content),
        ),
    )
    sources = _text_sources(notices)
    items: list[dict[str, Any]] = [
        _known_or_missing(
            "budget",
            "采购预算 / 最高限价",
            _budget_value(primary.budget, primary.budget_currency),
            "公告结构化字段" if primary.budget is not None else None,
        ),
        _known_or_missing(
            "deadline",
            "投标 / 响应截止",
            _datetime_value(primary.deadline),
            "公告结构化字段" if primary.deadline is not None else None,
        ),
    ]
    for key, label, keywords in _FIELD_RULES:
        match = _find_evidenced_excerpt(sources, keywords)
        items.append(
            _known_or_missing(
                key,
                label,
                match[0] if match else None,
                match[1] if match else None,
            )
        )
    return {
        "items": items,
        "contacts": _extract_contacts(sources),
    }


def _text_sources(notices: Sequence[TenderNotice]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for notice in notices:
        if notice.core_content:
            cleaned = sanitize_notice_text(notice.core_content, limit=200_000)
            if cleaned:
                values.append((f"{notice.source.source_name}公告正文", cleaned))
        for attachment in notice.attachments:
            if attachment.extracted_text:
                cleaned = sanitize_notice_text(attachment.extracted_text, limit=200_000)
                if cleaned:
                    values.append((attachment.name or "招标文件 PDF", cleaned))
    return values


def _find_evidenced_excerpt(
    sources: Sequence[tuple[str, str]],
    keywords: Sequence[str],
) -> tuple[str, str] | None:
    for source, text in sources:
        normalized = re.sub(r"\r\n?", "\n", text)
        segments = [
            re.sub(r"\s+", " ", segment).strip()
            for segment in re.split(r"[\n。；;]+", normalized)
        ]
        for segment in segments:
            if not segment or not any(keyword in segment for keyword in keywords):
                continue
            return _clip(segment, 190), source
    return None


def _extract_contacts(sources: Sequence[tuple[str, str]]) -> list[dict[str, str]]:
    contacts: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for source, text in sources:
        compact = re.sub(r"[\r\t]", " ", text)
        for match in _CONTACT.finditer(compact):
            window = compact[match.start() : match.start() + 180]
            phone_match = _PHONE.search(window)
            if phone_match is None:
                preceding = compact[max(0, match.start() - 80) : match.end()]
                phone_match = _PHONE.search(preceding)
            name = (match.group("name") or "").strip()
            if name in {"电话", "联系方式", "详见公告", "详见文件"}:
                name = ""
            phone = phone_match.group(0).replace(" ", "") if phone_match else ""
            if not name and not phone:
                continue
            key = (match.group("role"), name, phone)
            if key in seen:
                continue
            seen.add(key)
            contacts.append(
                {
                    "role": match.group("role"),
                    "name": name or "原文未具名",
                    "phone": phone or "原文未披露电话",
                    "source": source,
                }
            )
            if len(contacts) >= 6:
                return contacts
    return contacts


def _known_or_missing(
    key: str,
    label: str,
    value: str | None,
    source: str | None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value or "公告及已下载 PDF 未披露",
        "source": source or "未找到可核验原文",
        "available": bool(value),
    }


def _budget_value(value: Decimal | None, currency: str) -> str | None:
    if value is None:
        return None
    return f"{value:,.2f} {currency}"


def _datetime_value(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M")


def _clip(value: str, length: int) -> str:
    return value if len(value) <= length else f"{value[: length - 1]}…"


__all__ = ["build_bidder_insights"]
