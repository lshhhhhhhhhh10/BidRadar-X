from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.main import app
from app.storage import database as database_module


class SubscriptionsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database_patch = patch.object(
            database_module,
            "DATABASE_PATH",
            self.root / "app.db",
        )
        self.data_patch = patch.object(database_module, "DATA_DIR", self.root)
        self.database_patch.start()
        self.data_patch.start()

    def tearDown(self) -> None:
        self.data_patch.stop()
        self.database_patch.stop()
        self.temporary_directory.cleanup()

    def test_create_query_pause_resume_and_cancel_subscription(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(minutes=10)
        with TestClient(app) as client:
            created_response = client.post(
                "/api/subscriptions",
                json={
                    "query": "查询服务器采购公告",
                    "frequency": "once",
                    "timezone": "Asia/Shanghai",
                    "run_at": future.isoformat(),
                    "max_retries": 2,
                    "retry_backoff_seconds": 15,
                },
            )

            self.assertEqual(created_response.status_code, 201, created_response.text)
            created = created_response.json()
            task_id = created["task_id"]
            self.assertEqual(created["status"], "active")
            self.assertEqual(created["frequency"], "once")
            self.assertEqual(created["timezone"], "Asia/Shanghai")
            self.assertEqual(
                created["local_time"],
                future.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%H:%M"),
            )

            listed = client.get("/api/subscriptions")
            self.assertEqual(listed.status_code, 200)
            self.assertEqual([item["task_id"] for item in listed.json()["items"]], [task_id])

            fetched = client.get(f"/api/subscriptions/{task_id}")
            self.assertEqual(fetched.status_code, 200)
            self.assertEqual(fetched.json()["query"], "查询服务器采购公告")

            paused = client.post(f"/api/subscriptions/{task_id}/pause")
            self.assertEqual(paused.status_code, 200)
            self.assertEqual(paused.json()["status"], "paused")

            resumed = client.post(f"/api/subscriptions/{task_id}/resume")
            self.assertEqual(resumed.status_code, 200)
            self.assertEqual(resumed.json()["status"], "active")

            deleted = client.delete(f"/api/subscriptions/{task_id}")
            self.assertEqual(deleted.status_code, 204)
            self.assertEqual(client.get(f"/api/subscriptions/{task_id}").status_code, 404)

    def test_weekly_subscription_requires_a_weekday(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/subscriptions",
                json={
                    "query": "查询网络设备采购公告",
                    "frequency": "weekly",
                    "local_time": "09:00",
                },
            )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
