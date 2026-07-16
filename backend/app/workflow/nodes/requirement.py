from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ...schemas.tender import ScheduleSpec, TaskSpec
from .common import step


TOPIC_DICTIONARY = {
    "服务器": ["服务器", "机架式服务器", "GPU服务器", "计算节点", "存储服务器", "超融合设备"],
    "人工智能": ["人工智能", "AI平台", "大模型", "智能计算", "机器学习"],
}

CHINESE_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _parse_count(value: str) -> int:
    if value.isdigit():
        return max(1, int(value))
    if value == "十":
        return 10
    if "十" in value:
        left, right = value.split("十", 1)
        return CHINESE_DIGITS.get(left, 1) * 10 + CHINESE_DIGITS.get(right, 0)
    return CHINESE_DIGITS.get(value, 1)


def understand_requirement(state: dict[str, Any]) -> dict[str, Any]:
    query = state["query"]
    requested_region = (state.get("requested_region") or "").strip()
    if requested_region == "上海":
        requested_region = "上海市"
    detected_region = next(
        (name for name in ["安徽省", "江苏省", "浙江省", "上海市", "全国"] if name in query),
        None,
    )
    region = requested_region or detected_region
    requested_subject = (state.get("requested_subject") or "").strip()
    topic = requested_subject or next(
        (name for name in TOPIC_DICTIONARY if name in query), query[:24]
    )
    keywords = TOPIC_DICTIONARY.get(topic, [topic])
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    explicit_dates = [datetime.strptime(value, "%Y-%m-%d").date() for value in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", query)]
    relative_time = re.search(r"(?:最近|近)\s*([一二三四五六七八九十\d]+)\s*(天|周|个月|月|年)", query)
    if explicit_dates:
        first_date = min(explicit_dates)
        last_date = max(explicit_dates)
        range_start = datetime.combine(first_date, time.min, tzinfo=now.tzinfo)
        range_end = datetime.combine(last_date, time.max, tzinfo=now.tzinfo)
    elif relative_time:
        count = _parse_count(relative_time.group(1))
        days_per_unit = {"天": 1, "周": 7, "个月": 30, "月": 30, "年": 365}
        range_end = now
        range_start = now - timedelta(days=count * days_per_unit[relative_time.group(2)])
    else:
        range_start = None
        range_end = None

    task_spec = TaskSpec(
        task_id=state["task_id"],
        query=query,
        topic=topic,
        regions=[] if region in {None, "全国"} else [region],
        keywords=keywords,
        exclusions=["网站服务器故障", "游戏服务器", "不包含服务器"],
        time_range_start=range_start,
        time_range_end=range_end,
        schedule=ScheduleSpec(frequency=state["frequency"]),
    ).model_dump(mode="json")
    return {
        "task_spec": task_spec,
        "steps": step(state, "需求理解 Agent", f"识别主题“{topic}”、地区“{region or '未限定'}”和执行频率。"),
    }
