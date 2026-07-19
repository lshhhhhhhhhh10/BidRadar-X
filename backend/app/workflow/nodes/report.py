from __future__ import annotations

from typing import Any

from ...ai.service import AICoordinator
from ...ai.schemas import ReportDraft
from ...services.publisher import DeliveryPublishError, Publisher
from .common import step


_REPORT_PROJECT_BATCH_SIZE = 2
_REPORT_NOTICES_PER_PROJECT = 3
_REPORT_EVIDENCE_PER_PROJECT = 4


def generate_report(state: dict[str, Any]) -> dict[str, Any]:
    any_source_succeeded = any(
        source.get("collection_status") == "success"
        for source in state.get("selected_sources", [])
    )
    drafts: list[ReportDraft] = []
    audits: list[dict[str, Any]] = []
    skipped_audit: dict[str, Any] = {
        "prompt_id": "evidence-report",
        "prompt_version": "2.0.0",
        "status": "skipped",
        "reason": "no_changed_evidence",
    }
    if any_source_succeeded and state.get("changes") and state.get("evidence"):
        coordinator = AICoordinator()
        batches = _report_batches(state)
        # The provider applies an account-level concurrency limit and the client
        # already serializes requests.  A thread pool only created a burst of
        # queued calls and made 1302 rate-limit failures more likely.  Keep report
        # batches deliberately ordered so profile backoff/failover can work.
        results = [coordinator.draft_report(variables) for variables in batches]
        for draft, audit in results:
            audits.append(audit)
            if draft is not None:
                drafts.append(draft)
    ai_report: dict[str, Any] = {}
    if drafts:
        known_evidence = {item["evidence_id"] for item in state.get("evidence", [])}
        known_notice_ids = {
            document["notice"]["notice_id"]
            for project in state.get("projects", [])
            for document in project["documents"]
        }
        findings = [
            {
                "text": finding.text,
                "evidence_ids": [item for item in finding.evidence_ids if item in known_evidence],
            }
            for draft in drafts
            for finding in draft.key_findings
            if any(item in known_evidence for item in finding.evidence_ids)
        ]
        narratives = [
            {
                "notice_id": narrative.notice_id,
                "summary": narrative.summary,
                "risk_level": narrative.risk_level,
                "risk_assessment": narrative.risk_assessment,
                "risk_points": narrative.risk_points,
                "opportunity_points": narrative.opportunity_points,
                "next_actions": narrative.next_actions,
                "evidence_ids": [item for item in narrative.evidence_ids if item in known_evidence],
            }
            for draft in drafts
            for narrative in draft.notice_narratives
            if narrative.notice_id in known_notice_ids
            and any(item in known_evidence for item in narrative.evidence_ids)
        ]
        ai_report = {
            "status": "generated",
            "executive_summary": "；".join(
                draft.executive_summary.rstrip("。；") for draft in drafts
            ) + "。",
            "key_findings": findings,
            "notice_narratives": narratives,
            "generated_notice_count": len(narratives),
        }
    else:
        ai_report = {
            "status": "not_generated",
            "reason": _ai_report_failure_reason(audits, skipped_audit),
        }

    publisher = Publisher()
    if any_source_succeeded:
        try:
            report = publisher.publish({**state, "ai_report": ai_report})
        except DeliveryPublishError as error:
            report = {
                "status": "failed",
                "delivery_type": None,
                "filename": None,
                "download_url": None,
                "historical_report": None,
                "format": "docx",
                "report_scope": "incremental",
                "notice_count": 0,
                "reused_artifact": False,
                "delivery_fingerprint": error.delivery_fingerprint,
                "error_type": type(error.__cause__).__name__,
                "error": str(error),
                **publisher.source_outcomes(state),
            }
    else:
        report = {
            "status": "failed",
            "delivery_type": None,
            "filename": None,
            "download_url": None,
            "historical_report": None,
            "format": "docx",
            "report_scope": "incremental",
            "notice_count": 0,
            "reused_artifact": False,
            **publisher.source_outcomes(state),
        }
    return {
        "ai_report": ai_report,
        "ai_audit": [
            *state.get("ai_audit", []),
            *(audits or [skipped_audit]),
        ],
        "report": report,
        "status": "completed" if report["status"] in {"generated", "no_change"} else "failed",
        "steps": step(state, "报告生成 Agent", f"{'AI 已分批生成证据化摘要与风险研判，' if drafts else 'AI 调用未生成合格结果，已明确标注并'}使用去重后的真实公告字段生成并回读验证 DOCX。", len(state["changes"]), 1 if report["status"] == "generated" else 0, "completed" if report["status"] in {"generated", "no_change"} else "warning"),
    }


def _report_batches(state: dict[str, Any]) -> list[dict[str, Any]]:
    changed_project_ids = {
        str(item.get("project_id"))
        for item in state.get("changes", [])
        if item.get("project_id")
    }
    projects = [
        project
        for project in state.get("projects", [])
        if not changed_project_ids or project.get("project_id") in changed_project_ids
    ]
    analysis_by_project = {
        item.get("project_id"): item
        for item in state.get("analysis", [])
        if item.get("project_id")
    }
    evidence_by_project: dict[str, list[dict[str, Any]]] = {}
    for item in state.get("evidence", []):
        evidence_by_project.setdefault(str(item.get("project_id") or ""), []).append(item)

    batches: list[dict[str, Any]] = []
    for offset in range(0, len(projects), _REPORT_PROJECT_BATCH_SIZE):
        batch_projects = projects[offset : offset + _REPORT_PROJECT_BATCH_SIZE]
        project_ids = {str(project["project_id"]) for project in batch_projects}
        batch_evidence = []
        for project_id in project_ids:
            analysis = analysis_by_project.get(project_id, {})
            preferred_ids = set(analysis.get("evidence_ids", []))
            candidates = evidence_by_project.get(project_id, [])
            ordered = sorted(
                candidates,
                key=lambda item: (
                    item.get("evidence_id") not in preferred_ids,
                    -float(item.get("authority") or 0),
                ),
            )[:_REPORT_EVIDENCE_PER_PROJECT]
            batch_evidence.extend(
                {**item, "content": str(item.get("content") or "")[:900]}
                for item in ordered
            )
        batches.append(
            {
                "query": state["query"],
                "projects": [
                    {
                        "project_id": project["project_id"],
                        "title": project["title"],
                        "notices": [
                            {
                                "notice_id": document["notice"]["notice_id"],
                                "title": document["notice"]["title"],
                                "published_at": document["notice"]["published_at"],
                                "source_url": document["notice"]["source"]["source_url"],
                                "purchaser": document["notice"].get("purchaser"),
                                "budget": document["notice"].get("budget"),
                                "deadline": document["notice"].get("deadline"),
                                "core_content": document["notice"]["core_content"][:1000],
                            }
                            for document in project["documents"][:_REPORT_NOTICES_PER_PROJECT]
                        ],
                    }
                    for project in batch_projects
                ],
                "analysis": [
                    analysis_by_project[project_id]
                    for project_id in project_ids
                    if project_id in analysis_by_project
                ],
                "evidence": batch_evidence,
            }
        )
    return batches


def _ai_report_failure_reason(
    audits: list[dict[str, Any]],
    skipped_audit: dict[str, Any],
) -> str:
    if not audits:
        return str(skipped_audit.get("reason") or "AI 未执行")
    if any(item.get("status") == "disabled" for item in audits):
        return "AI 接口未启用"
    failure_reasons = [
        str(reason)
        for audit in audits
        for reason in _audit_failure_reasons(audit)
        if reason
    ]
    if failure_reasons:
        return failure_reasons[-1]
    return "AI 返回结果未通过结构与证据校验"


def _audit_failure_reasons(audit: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    own_reason = audit.get("failure_reason")
    if own_reason:
        reasons.append(str(own_reason))
    for attempt in audit.get("failover_attempts", []):
        if isinstance(attempt, dict) and attempt.get("failure_reason"):
            reasons.append(str(attempt["failure_reason"]))
    return reasons
