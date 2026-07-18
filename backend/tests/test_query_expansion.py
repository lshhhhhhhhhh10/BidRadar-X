from __future__ import annotations

import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.ai.config import clear_runtime_api_key
from app.workflow.nodes.query_expansion import expand_query
from app.workflow.nodes.requirement import understand_requirement
from app.workflow.nodes.search_plan import plan_search


class QueryExpansionTest(unittest.TestCase):
    def tearDown(self) -> None:
        clear_runtime_api_key()

    def test_server_query_expands_before_search_even_without_ai_key(self) -> None:
        state = {
            "task_id": str(uuid4()),
            "run_id": str(uuid4()),
            "query": "查询上海市服务器采购公告",
            "frequency": "once",
            "status": "running",
            "steps": [],
            "funnel": {},
            "retry_count": 0,
            "quality_passed": False,
            "quality_issues": [],
            "ai_audit": [],
        }
        with patch.dict(os.environ, {"BIDRADAR_AI_API_KEY": ""}, clear=False):
            understood = understand_requirement(state)
            expanded_state = {**state, **understood}
            expanded = expand_query(expanded_state)
            planned = plan_search({**expanded_state, **expanded})

        keywords = expanded["task_spec"]["keywords"]
        self.assertIn("服务器", keywords)
        self.assertIn("GPU服务器", keywords)
        self.assertIn("计算节点", keywords)
        self.assertLessEqual(len(keywords), 12)
        self.assertEqual(expanded["query_expansion"]["mode"], "dictionary")
        self.assertIn("检索扩词 Agent", expanded["steps"][-1]["name"])
        self.assertIn("GPU服务器", planned["search_plan"]["search_terms"])

    def test_unknown_topic_keeps_original_keyword_instead_of_cross_domain_expansion(self) -> None:
        state = {
            "task_spec": {
                "task_id": "task-custom",
                "query": "查询工业相机采购",
                "topic": "工业相机",
                "regions": [],
                "keywords": ["工业相机"],
                "exclusions": [],
                "time_range_start": None,
                "time_range_end": None,
                "schedule": {"frequency": "once", "timezone": "Asia/Shanghai"},
            },
            "steps": [],
            "ai_audit": [],
        }
        with patch.dict(os.environ, {"BIDRADAR_AI_API_KEY": ""}, clear=False):
            expanded = expand_query(state)

        self.assertEqual(expanded["task_spec"]["keywords"], ["工业相机"])
        self.assertNotIn("服务器", expanded["task_spec"]["keywords"])


if __name__ == "__main__":
    unittest.main()
