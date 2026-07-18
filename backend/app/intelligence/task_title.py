from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping


_UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_RELATIVE_TIME = re.compile(
    r"(?:最近|近|过去)\s*[一二三四五六七八九十百\d]+\s*(?:天|周|个月|月|年)"
)
_EXPLICIT_DATE = re.compile(
    r"20\d{2}(?:[-./年]\d{1,2}(?:[-./月]\d{1,2}日?)?)?"
)
_REGION = re.compile(
    r"(?:全国|北京市|天津市|上海市|重庆市|"
    r"(?:河北|山西|辽宁|吉林|黑龙江|江苏|浙江|安徽|福建|江西|山东|河南|湖北|湖南|广东|海南|四川|贵州|云南|陕西|甘肃|青海|台湾)省|"
    r"(?:内蒙古|广西|西藏|宁夏|新疆)(?:壮族|回族|维吾尔)?自治区|"
    r"香港特别行政区|澳门特别行政区)"
)


def summarized_task_title(
    task_spec: Mapping[str, Any] | None,
    *,
    fallback_query: str = "",
) -> str:
    """Create a short history/archive title from normalized intent, not raw input."""

    spec = dict(task_spec or {})
    topic = _topic_context(_clean_phrase(str(spec.get("topic") or "")))
    regions = [
        _clean_phrase(str(value))
        for value in spec.get("regions", [])
        if _clean_phrase(str(value))
    ]
    if not regions:
        regions = _regions_from_query(fallback_query)
    region = "、".join(dict.fromkeys(regions[:2]))
    if not topic:
        topic = _topic_context(_fallback_topic(fallback_query))
    if not topic:
        topic = "招投标机会"

    time_context = _time_context(spec, fallback_query)
    parts = [part for part in (time_context, region, topic) if part]
    title = " · ".join(dict.fromkeys(parts))
    return title[:42]


def _fallback_topic(value: str) -> str:
    value = _UUID.sub("", value)
    value = re.sub(r"^(?:请|帮我|请帮我|查询|查找|检索|寻找|追踪|监控)+", "", value)
    value = _RELATIVE_TIME.sub("", value)
    value = _EXPLICIT_DATE.sub("", value)
    value = _REGION.sub("", value)
    value = re.sub(r"(?:每天|每周|每月).*$", "", value)
    value = re.sub(r"(?:招标)?(?:公告|信息|有哪些|都有哪(?:些)?)$", "", value)
    return _clean_phrase(value)


def _topic_context(value: str) -> str:
    value = re.sub(r"(?:公告|信息|有哪些|都有哪(?:些)?|查询|检索)+$", "", value).strip()
    if not value:
        return ""
    if re.search(r"(?:项目|服务|工程|采购|招标|建设|维护|改造|设备|系统)$", value):
        return value
    return f"{value}采购"


def _regions_from_query(value: str) -> list[str]:
    return list(dict.fromkeys(match.group(0) for match in _REGION.finditer(value)))


def _time_context(spec: Mapping[str, Any], fallback_query: str) -> str:
    relative = _RELATIVE_TIME.search(fallback_query)
    if relative:
        return re.sub(r"\s+", "", relative.group(0))
    explicit = _EXPLICIT_DATE.search(fallback_query)
    if explicit:
        return _display_date(explicit.group(0))

    start = _parse_datetime(spec.get("time_range_start"))
    end = _parse_datetime(spec.get("time_range_end"))
    if start and end:
        if start.date() == end.date():
            return start.strftime("%Y.%m.%d")
        if start.year == end.year:
            return f"{start:%Y.%m.%d}–{end:%m.%d}"
        return f"{start:%Y.%m.%d}–{end:%Y.%m.%d}"
    if start:
        return f"{start:%Y.%m.%d}起"
    if end:
        return f"截至{end:%Y.%m.%d}"
    return ""


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _display_date(value: str) -> str:
    numbers = re.findall(r"\d+", value)
    return ".".join(
        number.zfill(2) if index > 0 else number
        for index, number in enumerate(numbers)
    )


def _clean_phrase(value: str) -> str:
    value = _UUID.sub("", value)
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"[，,。；;：:？?！!]+", "", value)
    return value.strip("-_·")[:36]


__all__ = ["summarized_task_title"]
