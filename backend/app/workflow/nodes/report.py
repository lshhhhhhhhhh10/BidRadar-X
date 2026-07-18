from __future__ import annotations

from typing import Any

from ...ai.service import AICoordinator, append_audit
from ...services.publisher import DeliveryPublishError, Publisher
from .common import step


def generate_report(state: dict[str, Any]) -> dict[str, Any]:
    any_source_succeeded = any(
        source.get("collection_status") == "success"
        for source in state.get("selected_sources", [])
    )
    draft = None
    audit: dict[str, Any] = {
        "prompt_id": "evidence-report",
        "prompt_version": "1.0.0",
        "status": "skipped",
        "reason": "no_changed_evidence",
    }
    if any_source_succeeded and state.get("changes") and state.get("evidence"):
        coordinator = AICoordinator()
        draft, audit = coordinator.draft_report(
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
                            "core_content": document["notice"]["core_content"][:2000],
                        }
                        for document in project["documents"]
                    ],
                }
                for project in state.get("projects", [])[:40]
            ],
            "analysis": state.get("analysis", []),
            "evidence": [
                {**item, "content": item["content"][:1800]}
                for item in state.get("evidence", [])[:80]
            ],
            }
        )
    ai_report: dict[str, Any] = {}
    if draft is not None:
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
            for finding in draft.key_findings
            if any(item in known_evidence for item in finding.evidence_ids)
        ]
        narratives = [
            {
                "notice_id": narrative.notice_id,
                "summary": narrative.summary,
                "risk_points": narrative.risk_points,
                "next_actions": narrative.next_actions,
                "evidence_ids": [item for item in narrative.evidence_ids if item in known_evidence],
            }
            for narrative in draft.notice_narratives
            if narrative.notice_id in known_notice_ids
            and any(item in known_evidence for item in narrative.evidence_ids)
        ]
        ai_report = {
            "status": "generated",
            "executive_summary": draft.executive_summary,
            "key_findings": findings,
            "notice_narratives": narratives,
        }
    else:
        ai_report = {"status": "not_generated"}

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
        "ai_audit": append_audit(state, audit),
        "report": report,
        "status": "completed" if report["status"] in {"generated", "no_change"} else "failed",
        "steps": step(state, "报告生成 Agent", f"{'AI 生成证据化摘要后，' if draft is not None else ''}使用去重后的真实公告字段生成并回读验证 DOCX。", len(state["changes"]), 1 if report["status"] == "generated" else 0, "completed" if report["status"] in {"generated", "no_change"} else "warning"),
    }
