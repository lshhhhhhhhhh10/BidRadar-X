from __future__ import annotations

from typing import Any

from .common import step


def verify_facts(state: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    if not state["analysis"]:
        issues.append("没有获得满足主题条件的项目")
    for item in state["analysis"]:
        if not item["evidence_ids"]:
            issues.append(f"{item['project_id']} 缺少证据")
    passed = not issues
    retry_count = state.get("retry_count", 0) + (0 if passed else 1)
    return {
        "quality_passed": passed,
        "quality_issues": issues,
        "retry_count": retry_count,
        "steps": step(state, "事实核验 Agent", "质量检查通过。" if passed else "质量不足，将触发一次检索回路。", len(state["analysis"]), len(state["analysis"]) - len(issues), "completed" if passed else "warning"),
    }
