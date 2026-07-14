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


def understand_requirement(state: dict[str, Any]) -> dict[str, Any]:
    query = state["query"]
    region = next((name for name in ["安徽省", "江苏省", "浙江省", "上海市", "全国"] if name in query), None)
    topic = next((name for name in TOPIC_DICTIONARY if name in query), query[:24])
    keywords = TOPIC_DICTIONARY.get(topic, [topic])
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    explicit_dates = [datetime.strptime(value, "%Y-%m-%d").date() for value in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", query)]
    if explicit_dates:
        first_date = min(explicit_dates)
        last_date = max(explicit_dates)
        range_start = datetime.combine(first_date, time.min, tzinfo=now.tzinfo)
        range_end = datetime.combine(last_date, time.max, tzinfo=now.tzinfo)
    else:
        range_end = now
        range_start = now - timedelta(days=30)

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
