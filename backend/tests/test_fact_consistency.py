from __future__ import annotations

import unittest

from app.intelligence.fact_consistency import FactConsistencyValidator
from tests.integration_support import make_notice


def _state(*, unsupported_summary: bool = False) -> dict:
    notice = make_notice(
        source_id="annotated-source",
        source_name="人工标注样本来源",
        source_url="https://example.gov.cn/notices/001",
        marker="a",
    )
    project_id = "annotated-project"
    evidence_id = "ev-annotated"
    return {
        "projects": [{
            "project_id": project_id,
            "documents": [{"notice": notice.model_dump(mode="json")}],
        }],
        "evidence": [{
            "evidence_id": evidence_id,
            "project_id": project_id,
            "content": notice.core_content,
        }],
        "analysis": [{
            "project_id": project_id,
            "summary": "原文没有的虚构事实" if unsupported_summary else notice.core_content[:12],
            "facts": {"budget": None, "deadline": None, "purchaser": None},
            "evidence_ids": [evidence_id],
        }],
    }


class FactConsistencyTest(unittest.TestCase):
    def test_supported_development_annotation_passes(self) -> None:
        result = FactConsistencyValidator().validate(_state())
        self.assertTrue(result.passed)
        self.assertEqual(result.support_rate, 1.0)

    def test_unsupported_generated_claim_is_rejected(self) -> None:
        result = FactConsistencyValidator().validate(_state(unsupported_summary=True))
        self.assertFalse(result.passed)
        self.assertLess(result.support_rate, 1.0)
        self.assertTrue(any("摘要" in issue for issue in result.unsupported_claims))


if __name__ == "__main__":
    unittest.main()
