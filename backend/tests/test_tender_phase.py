from __future__ import annotations

from datetime import datetime
import unittest
from unittest.mock import patch

from app.intelligence.tender_phase import evaluate_tender_phase
from app.schemas.tender import EvidenceReference, SourceRecord, TenderNotice
from app.workflow.nodes.relevance import judge_relevance


REFERENCE_TIME = datetime.fromisoformat("2026-07-17T19:00:00+08:00")


def make_notice(
    *,
    notice_type: str = "tender",
    title: str = "服务器采购项目公开招标公告",
    core_content: str = "现对服务器采购项目进行公开招标，欢迎合格供应商参加。",
    deadline: str | None = "2026-07-25T10:00:00+08:00",
) -> TenderNotice:
    evidence = []
    if deadline is not None:
        evidence.append(
            EvidenceReference(
                evidence_id="evidence-deadline",
                field_path="deadline",
                source_url="https://example.gov.cn/notices/001",
                quote=f"投标截止时间为 {deadline}",
                fetched_at=REFERENCE_TIME,
            )
        )
    return TenderNotice(
        notice_id="notice-001",
        notice_type=notice_type,
        title=title,
        published_at="2026-07-17T09:00:00+08:00",
        source=SourceRecord(
            source_id="official-source",
            source_name="政府采购平台",
            source_url="https://example.gov.cn/notices/001",
            publication_role="original",
        ),
        core_content=core_content,
        deadline=deadline,
        raw_content_fingerprint="1" * 64,
        notice_stable_fingerprint="2" * 64,
        project_stable_fingerprint="3" * 64,
        fetched_at=REFERENCE_TIME,
        evidence=evidence,
    )


class TenderPhaseTest(unittest.TestCase):
    def test_keeps_an_active_tender(self) -> None:
        decision = evaluate_tender_phase(make_notice(), as_of=REFERENCE_TIME)
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.reason, "active_tender")

    def test_rejects_awarded_and_cancelled_lifecycle_types(self) -> None:
        for notice_type in ("award", "cancellation"):
            with self.subTest(notice_type=notice_type):
                decision = evaluate_tender_phase(
                    make_notice(notice_type=notice_type),
                    as_of=REFERENCE_TIME,
                )
                self.assertFalse(decision.accepted)

    def test_rejects_terminal_titles_even_when_source_misclassifies_them(self) -> None:
        for title in (
            "服务器采购项目中标结果公告",
            "服务器采购项目流标公告",
            "服务器采购项目废标公告",
            "服务器采购项目终止公告",
        ):
            with self.subTest(title=title):
                decision = evaluate_tender_phase(
                    make_notice(title=title),
                    as_of=REFERENCE_TIME,
                )
                self.assertFalse(decision.accepted)

    def test_rejects_a_notice_after_its_submission_deadline(self) -> None:
        decision = evaluate_tender_phase(
            make_notice(deadline="2026-07-17T18:59:59+08:00"),
            as_of=REFERENCE_TIME,
        )
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "deadline_passed")

    def test_keeps_active_correction_but_rejects_award_correction(self) -> None:
        active = evaluate_tender_phase(
            make_notice(notice_type="correction", title="服务器采购项目更正公告"),
            as_of=REFERENCE_TIME,
        )
        award = evaluate_tender_phase(
            make_notice(notice_type="correction", title="服务器采购项目中标结果更正公告"),
            as_of=REFERENCE_TIME,
        )
        self.assertTrue(active.accepted)
        self.assertFalse(award.accepted)

    def test_workflow_filters_terminal_notice_before_semantic_review(self) -> None:
        active = make_notice()
        awarded = TenderNotice.model_validate({
            **active.model_dump(mode="json"),
            "notice_id": "notice-awarded",
            "notice_type": "tender",
            "title": "服务器采购项目中标结果公告",
            "raw_content_fingerprint": "4" * 64,
            "notice_stable_fingerprint": "5" * 64,
        })
        state = {
            "task_spec": {"keywords": ["服务器"], "exclusions": []},
            "normalized_documents": [
                active.model_dump(mode="json"),
                awarded.model_dump(mode="json"),
            ],
            "funnel": {"normalized": 2},
            "steps": [],
            "ai_audit": [],
        }

        with patch(
            "app.workflow.nodes.relevance.AICoordinator.review_relevance",
            return_value=(None, {"status": "disabled"}),
        ) as review:
            result = judge_relevance(state)

        self.assertEqual(result["funnel"]["active_tender"], 1)
        self.assertEqual(
            [item["notice_id"] for item in result["relevant_documents"]],
            [active.notice_id],
        )
        candidates = review.call_args.args[0]["candidates"]
        self.assertEqual([item["notice_id"] for item in candidates], [active.notice_id])

    def test_workflow_skips_paid_semantic_review_when_all_candidates_are_terminal(self) -> None:
        awarded = make_notice(
            notice_type="award",
            title="服务器采购项目中标结果公告",
        )
        state = {
            "task_spec": {"keywords": ["服务器"], "exclusions": []},
            "normalized_documents": [awarded.model_dump(mode="json")],
            "funnel": {"normalized": 1},
            "steps": [],
            "ai_audit": [],
        }

        with patch(
            "app.workflow.nodes.relevance.AICoordinator.review_relevance",
        ) as review:
            result = judge_relevance(state)

        review.assert_not_called()
        self.assertEqual(result["relevant_documents"], [])
        self.assertEqual(result["funnel"]["active_tender"], 0)


if __name__ == "__main__":
    unittest.main()
