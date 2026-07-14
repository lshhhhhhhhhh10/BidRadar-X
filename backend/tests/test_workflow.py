import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.services import publisher as publisher_module
from app.workflow.graph import WORKFLOW
from app.workflow.nodes import source_select
from tests.integration_support import isolated_source_set


class WorkflowTest(unittest.TestCase):
    def test_real_contract_workflow_reaches_docx_report(self) -> None:
        adapters = isolated_source_set()
        with tempfile.TemporaryDirectory() as output_dir:
            with (
                patch.object(source_select, "SOURCE_ADAPTERS", adapters),
                patch.object(publisher_module, "REPORT_DIR", Path(output_dir)),
            ):
                state = asyncio.run(
                    WORKFLOW.ainvoke(
                        {
                            "task_id": str(uuid4()),
                            "run_id": str(uuid4()),
                            "query": "查询 2026-07-14 全国服务器采购公告",
                            "frequency": "once",
                            "status": "running",
                            "steps": [],
                            "funnel": {},
                            "retry_count": 0,
                            "quality_passed": False,
                            "quality_issues": [],
                        }
                    )
                )

            self.assertEqual(state["status"], "completed")
            self.assertTrue(state["quality_passed"])
            self.assertEqual(len(state["projects"]), 1)
            self.assertTrue(state["report"]["filename"].endswith(".docx"))
            self.assertEqual(state["report"]["source_count"], 3)


if __name__ == "__main__":
    unittest.main()
