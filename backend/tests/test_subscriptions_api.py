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
from app.storage.repository import Repository


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

    def test_natural_language_query_creates_a_persisted_daily_subscription(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/subscriptions/from-query",
                json={"query": "每天上午9点查询安徽省服务器采购项目"},
            )

            self.assertEqual(response.status_code, 201, response.text)
            body = response.json()
            created = body["subscription"]
            parsed = body["parsed"]
            self.assertEqual(parsed["frequency"], "daily")
            self.assertEqual(parsed["local_time"], "09:00")
            self.assertEqual(parsed["search_query"], "查询安徽省服务器采购项目")
            self.assertEqual(created["query"], parsed["search_query"])
            self.assertEqual(created["timezone"], "Asia/Shanghai")

            listed = client.get("/api/subscriptions").json()["items"]
            self.assertEqual([item["task_id"] for item in listed], [created["task_id"]])

    def test_natural_language_query_creates_a_weekly_subscription(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/subscriptions/from-query",
                json={"query": "每周一下午3点查询上海市计算设备采购"},
            )

        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["parsed"]["frequency"], "weekly")
        self.assertEqual(body["parsed"]["weekly_day"], "monday")
        self.assertEqual(body["parsed"]["local_time"], "15:00")
        self.assertEqual(body["subscription"]["weekly_day"], "monday")

    def test_natural_language_query_creates_a_three_minute_subscription(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/subscriptions/from-query",
                json={"query": "每隔三分钟查询全国人工智能采购信息"},
            )

        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["parsed"]["frequency"], "interval")
        self.assertEqual(body["parsed"]["interval_minutes"], 3)
        self.assertEqual(body["parsed"]["search_query"], "查询全国人工智能采购信息")
        self.assertEqual(body["subscription"]["interval_minutes"], 3)
        next_run = datetime.fromisoformat(body["subscription"]["next_run_at"])
        created_at = datetime.fromisoformat(body["subscription"]["created_at"])
        self.assertAlmostEqual((next_run - created_at).total_seconds(), 180, delta=2)

    def test_subscription_detail_lists_new_and_empty_triggers(self) -> None:
        with TestClient(app) as client:
            created = client.post(
                "/api/subscriptions/from-query",
                json={"query": "每隔三分钟查询全国人工智能采购信息"},
            ).json()["subscription"]
            task_id = created["task_id"]
            earlier = datetime.now(timezone.utc) - timedelta(minutes=6)
            later = datetime.now(timezone.utc) - timedelta(minutes=3)
            with database_module.connect() as connection:
                connection.executemany(
                    """
                    INSERT INTO schedule_runs(
                        run_id, task_id, scheduled_for, worker_id, status,
                        retry_count, started_at, completed_at, error
                    ) VALUES (?, ?, ?, 'test-worker', 'succeeded', 0, ?, ?, NULL)
                    """,
                    [
                        ("new-run", task_id, earlier.isoformat(), earlier.isoformat(), earlier.isoformat()),
                        ("empty-run", task_id, later.isoformat(), later.isoformat(), later.isoformat()),
                    ],
                )
            Repository().save_run(
                {
                    "task_id": task_id,
                    "run_id": "new-run",
                    "query": created["query"],
                    "frequency": "interval",
                    "status": "completed",
                    "changes": [{"project_id": "project-1", "type": "new_project"}],
                    "projects": [
                        {
                            "project_id": "project-1",
                            "documents": [
                                {
                                    "notice": {
                                        "title": "人工智能算力平台采购项目",
                                        "published_at": "2026-07-18T09:00:00+08:00",
                                        "core_content": "采购人工智能算力服务器。",
                                        "source": {
                                            "source_name": "中国政府采购网",
                                            "source_url": "https://example.test/project-1",
                                            "authority": 1,
                                        },
                                    }
                                }
                            ],
                        }
                    ],
                    "report": {"status": "generated"},
                }
            )

            response = client.get(f"/api/subscriptions/{task_id}/detail")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["subscription"]["task_id"], task_id)
        self.assertEqual([item["run_id"] for item in body["runs"]], ["empty-run", "new-run"])
        self.assertEqual(body["runs"][0]["outcome"], "no_change")
        self.assertEqual(body["runs"][0]["project_count"], 0)
        self.assertEqual(body["runs"][1]["outcome"], "new_content")
        self.assertEqual(body["runs"][1]["projects"][0]["title"], "人工智能算力平台采购项目")
        self.assertTrue(body["runs"][1]["report_available"])

    def test_natural_language_once_subscription_survives_service_restart(self) -> None:
        local_future = datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(days=2)
        query = f"{local_future:%Y-%m-%d} 上午9点查询安徽服务器采购"
        with TestClient(app) as client:
            response = client.post(
                "/api/subscriptions/from-query",
                json={"query": query},
            )
            self.assertEqual(response.status_code, 201, response.text)
            created = response.json()["subscription"]

        with TestClient(app) as restarted_client:
            restored = restarted_client.get(
                f"/api/subscriptions/{created['task_id']}"
            )

        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["frequency"], "once")
        self.assertEqual(restored.json()["run_at"], created["run_at"])
        self.assertGreater(
            datetime.fromisoformat(created["run_at"]),
            datetime.now(timezone.utc),
        )

    def test_invalid_natural_language_requests_do_not_create_subscriptions(self) -> None:
        cases = {
            "": "schedule_not_found",
            "查": "schedule_not_found",
            "查询服务器项目": "schedule_not_found",
            "每天查询服务器项目": "schedule_invalid",
            "每天25点查询服务器项目": "schedule_invalid",
            "每周一周二9点查询服务器项目": "schedule_ambiguous",
            "2000-01-01 上午9点查询服务器项目": "schedule_in_past",
            "每天上午9点": "empty_search_query",
            "每隔2分钟查询服务器项目": "interval_too_short",
        }

        with TestClient(app) as client:
            for query, expected_code in cases.items():
                with self.subTest(query=query):
                    response = client.post(
                        "/api/subscriptions/from-query",
                        json={"query": query},
                    )
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertEqual(response.json()["detail"]["code"], expected_code)

            self.assertEqual(client.get("/api/subscriptions").json()["items"], [])


if __name__ == "__main__":
    unittest.main()
