from __future__ import annotations

from typing import Any

from ...ai.service import AICoordinator, append_audit
from ...intelligence.tender_phase import evaluate_tender_phase
from ...schemas.tender import TenderNotice
from .common import step


def judge_relevance(state: dict[str, Any]) -> dict[str, Any]:
    keywords = state["task_spec"]["keywords"]
    exclusions = state["task_spec"]["exclusions"]
    normalized_notices = [
        TenderNotice.model_validate(payload) for payload in state["normalized_documents"]
    ]
    phase_decisions = {
        notice.notice_id: evaluate_tender_phase(notice)
        for notice in normalized_notices
    }
    notices = [
        notice
        for notice in normalized_notices
        if phase_decisions[notice.notice_id].accepted
    ]
    rule_relevant_ids: set[str] = set()
    rule_matches: dict[str, list[str]] = {}
    for notice in notices:
        searchable = f"{notice.title} {notice.core_content}"
        matched = [keyword for keyword in keywords if keyword.casefold() in searchable.casefold()]
        excluded = [phrase for phrase in exclusions if phrase in searchable]
        if matched and not excluded:
            rule_relevant_ids.add(notice.notice_id)
            rule_matches[notice.notice_id] = matched

    coordinator = AICoordinator()
    if notices:
        review, audit = coordinator.review_relevance(
            {
                "task_spec": state["task_spec"],
                "candidates": [
                    {
                        "notice_id": notice.notice_id,
                        "title": notice.title,
                        "region": notice.region,
                        "published_at": notice.published_at.isoformat(),
                        "content": notice.core_content[:1600],
                        "rule_matched_terms": rule_matches.get(notice.notice_id, []),
                    }
                    for notice in notices[:40]
                ],
            }
        )
    else:
        review = None
        audit = {
            "stage": "relevance",
            "status": "skipped",
            "reason": "no_active_tender_candidates",
        }
    ai_used = review is not None
    accepted_ids = set(rule_relevant_ids)
    if review is not None:
        notice_searchable = {
            notice.notice_id: f"{notice.title} {notice.core_content}".casefold()
            for notice in notices
        }
        for decision in review.decisions:
            searchable = notice_searchable.get(decision.notice_id)
            if searchable is None:
                continue
            authentic_terms = [
                term for term in decision.matched_terms if term.casefold() in searchable
            ]
            if (
                decision.notice_id not in rule_relevant_ids
                and decision.relevant
                and decision.confidence >= 0.80
                and authentic_terms
            ):
                accepted_ids.add(decision.notice_id)
            elif (
                decision.notice_id in rule_relevant_ids
                and not decision.relevant
                and decision.confidence >= 0.92
            ):
                accepted_ids.discard(decision.notice_id)

    relevant = [
        notice.model_dump(mode="json")
        for notice in notices
        if notice.notice_id in accepted_ids
    ]
    funnel = {
        **state["funnel"],
        "active_tender": len(notices),
        "relevant": len(relevant),
    }
    removed_count = len(normalized_notices) - len(notices)
    return {
        "relevant_documents": relevant,
        "funnel": funnel,
        "ai_audit": append_audit(state, audit),
        "steps": step(
            state,
            "相关性判断 Agent",
            (
                f"先排除 {removed_count} 条已中标、流废标、终止或已过截止期公告，"
                f"再通过规则初筛{'与 AI 语义复核' if ai_used else ''}筛选契约化公告。"
            ),
            len(state["normalized_documents"]),
            len(relevant),
        ),
    }
