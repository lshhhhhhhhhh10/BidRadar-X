import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.services.publisher import REPORT_DIR
from app.workflow.nodes import source_select
from tests.integration_support import isolated_source_set


class ApiTest(unittest.TestCase):
    def test_run_returns_downloadable_docx_and_source_outcomes(self) -> None:
        client = TestClient(app)
        adapters = isolated_source_set()
        query = f"查询全国服务器采购公告 {uuid4()}"

        with (
            patch.object(source_select, "SOURCE_ADAPTERS", adapters),
        ):
            response = client.post(
                "/api/tasks/run",
                json={"query": query, "frequency": "once"},
            )
            repeated_response = client.post(
                "/api/tasks/run",
                json={"query": query, "frequency": "once"},
            )
            other_task_response = client.post(
                "/api/tasks/run",
                json={"query": query, "frequency": "weekly"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        report = payload["report"]
        self.assertEqual(report["status"], "generated")
        self.assertEqual(report["delivery_type"], "full_snapshot")
        self.assertTrue(report["filename"].endswith(".docx"))
        self.assertEqual(report["source_count"], 3)
        self.assertEqual(len(report["successful_sources"]), 2)
        self.assertEqual(len(report["failed_sources"]), 1)
        self.assertEqual(
            report["download_url"],
            f"/api/reports/{report['delivery_fingerprint']}/download",
        )

        download = client.get(report["download_url"])
        self.assertEqual(download.status_code, 200)
        self.assertEqual(
            download.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertTrue(download.content.startswith(b"PK"))

        self.assertEqual(repeated_response.status_code, 200, repeated_response.text)
        repeated_report = repeated_response.json()["report"]
        self.assertEqual(repeated_report["status"], "no_change")
        self.assertIsNone(repeated_report["filename"])
        self.assertIsNone(repeated_report["download_url"])
        self.assertEqual(repeated_report["notice_count"], 0)
        self.assertEqual(repeated_report["report_scope"], "incremental")
        self.assertFalse(repeated_report["reused_artifact"])
        self.assertEqual(
            repeated_report["historical_report"]["filename"],
            report["filename"],
        )
        self.assertEqual(
            client.get(repeated_report["historical_report"]["download_url"]).status_code,
            200,
        )

        self.assertEqual(other_task_response.status_code, 200, other_task_response.text)
        other_task_report = other_task_response.json()["report"]
        self.assertNotEqual(other_task_report["filename"], report["filename"])
        self.assertFalse(other_task_report["reused_artifact"])

        (REPORT_DIR / report["filename"]).unlink(missing_ok=True)
        (REPORT_DIR / other_task_report["filename"]).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
