from __future__ import annotations

from typing import Any

from ...services.scheduler import LocalScheduler
from .common import step


def plan_task(state: dict[str, Any]) -> dict[str, Any]:
    scheduler = LocalScheduler()
    monitor_plan = {
        "mode": "initial_query" if state["frequency"] == "once" else "continuous_monitoring",
        "frequency": state["frequency"],
        "next_run_at": scheduler.next_run_at(state["frequency"]),
        "watermark_scope": "per_source",
        "delivery_rule": "new_event_or_material_change",
    }
    return {
        "monitor_plan": monitor_plan,
        "steps": step(state, "监控任务与约束计划", "生成首次查询、来源水位线和增量推送约束。"),
    }
