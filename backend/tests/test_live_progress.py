from __future__ import annotations

import unittest

from app.services.live_progress import build_live_progress


class LiveProgressTests(unittest.TestCase):
    def test_empty_search_uses_cross_states_instead_of_success(self) -> None:
        state = {
            "query": "不存在的服务器项目",
            "task_spec": {"topic": "服务器", "regions": ["全国"]},
            "query_expansion": {"added_keywords": ["算力服务器"]},
            "selected_sources": [
                {
                    "source_id": "ccgp",
                    "name": "中国政府采购网",
                    "collection_status": "success",
                    "record_count": 0,
                }
            ],
            "raw_documents": [],
            "relevant_documents": [],
            "projects": [],
            "changes": [],
            "report": {"status": "no_change", "project_documents": []},
        }

        progress = build_live_progress(state, lifecycle="empty")

        stages = {stage["id"]: stage for stage in progress["stages"]}
        self.assertEqual(stages["sources"]["status"], "empty")
        self.assertEqual(stages["cleaning"]["status"], "empty")
        self.assertEqual(stages["documents"]["status"], "empty")
        self.assertEqual(stages["sources"]["details"]["sources"][0]["status"], "empty")

    def test_source_counts_use_nested_source_evidence(self) -> None:
        state = {
            "task_spec": {"topic": "服务器"},
            "query_expansion": {},
            "selected_sources": [
                {
                    "source_id": "ccgp",
                    "name": "中国政府采购网",
                    "collection_status": "success",
                    "record_count": 4,
                }
            ],
            "raw_documents": [{"id": "1"}],
            "relevant_documents": [
                {"source": {"source_id": "ccgp"}, "title": "服务器采购公告"}
            ],
        }

        progress = build_live_progress(state)

        source = progress["stages"][2]["details"]["sources"][0]
        self.assertEqual(source["status"], "success")
        self.assertEqual(source["relevant_count"], 1)

    def test_ai_badge_only_claims_completed_real_call(self) -> None:
        state = {
            "task_spec": {"topic": "服务器"},
            "ai_audit": [
                {
                    "prompt_id": "intent-extraction",
                    "status": "completed",
                    "model": "glm-5.2",
                    "latency_ms": 321,
                },
                {
                    "prompt_id": "query-expansion",
                    "status": "failed",
                    "model": "glm-5.2",
                },
            ],
        }

        progress = build_live_progress(state)

        self.assertEqual(progress["stages"][0]["ai"]["label"], "AI 已真实调用")
        self.assertEqual(progress["stages"][0]["ai"]["latency_ms"], 321)
        self.assertEqual(
            progress["stages"][1]["ai"]["label"],
            "AI 未成功，已使用规则兜底",
        )

    def test_source_failure_exposes_a_safe_specific_reason(self) -> None:
        state = {
            "task_spec": {"topic": "服务器"},
            "query_expansion": {},
            "selected_sources": [
                {
                    "source_id": "ggzy-national",
                    "name": "全国公共资源交易平台",
                    "collection_status": "failed",
                    "record_count": 0,
                    "error_type": "GGZYHTTPError",
                    "error": "unexpected HTTP status 503 for https://www.ggzy.gov.cn/",
                }
            ],
            "raw_documents": [],
            "relevant_documents": [],
        }

        progress = build_live_progress(state, lifecycle="failed")

        source = progress["stages"][2]["details"]["sources"][0]
        self.assertEqual(source["failure_reason"], "官网返回 HTTP 503，自动重试未恢复")


if __name__ == "__main__":
    unittest.main()
