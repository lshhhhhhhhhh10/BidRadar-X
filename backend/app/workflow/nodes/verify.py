from __future__ import annotations

from typing import Any

from ...ai.service import AICoordinator, append_audit
from ...intelligence.fact_consistency import FactConsistencyValidator
from .common import step


def verify_facts(state: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    if not state["analysis"]:
        issues.append("没有获得满足主题条件的项目")
    for item in state["analysis"]:
        if not item["evidence_ids"]:
            issues.append(f"{item['project_id']} 缺少证据")
    consistency = FactConsistencyValidator().validate(state)
    issues.extend(consistency.unsupported_claims)
    audit = None
    ai_used = False
    if state["analysis"]:
        coordinator = AICoordinator()
        verification, audit = coordinator.verify_facts(
            {
                "query": state["query"],
                "analysis": state["analysis"],
                "evidence": [
                    {**item, "content": item["content"][:1800]}
                    for item in state["evidence"][:60]
                ],
            }
        )
        ai_used = verification is not None
        if verification is not None:
            known_projects = {item["project_id"] for item in state["analysis"]}
            for project in verification.projects:
                if (
                    project.project_id in known_projects
                    and not project.supported
                    and project.confidence >= 0.80
                    and project.unsupported_claims
                ):
                    issues.append(
                        f"{project.project_id} AI 核验未通过：{'; '.join(project.unsupported_claims[:3])}"
                    )
    passed = not issues
    retry_count = state.get("retry_count", 0) + (0 if passed else 1)
    return {
        "quality_passed": passed,
        "quality_issues": issues,
        "fact_consistency": consistency.as_dict(),
        "retry_count": retry_count,
        **({"ai_audit": append_audit(state, audit)} if audit is not None else {}),
        "steps": step(state, "事实核验 Agent", ("规则与 AI 双重核验通过。" if ai_used else "规则核验通过。") if passed else "质量不足，将自动触发一次检索回路。", len(state["analysis"]), max(0, len(state["analysis"]) - len(issues)), "completed" if passed else "warning"),
    }
