from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.integrations.feishu import (
    DEFAULT_FIELD_MAP,
    FeishuBitableClient,
    FeishuConfig,
    FeishuDeliveryService,
    FeishuError,
    PROVIDER_ID,
)
from app.storage import database as database_module
from app.storage.repository import Repository


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def request(self, method, url, *, headers=None, payload=None, timeout=15):
        self.calls.append({
            "method": method,
            "url": url,
            "headers": headers,
            "payload": payload,
            "timeout": timeout,
        })
        if url.endswith("/tenant_access_token/internal"):
            return {"code": 0, "tenant_access_token": "tenant-token", "expire": 7200}
        if "fields?page_size=100" in url:
            return {
                "code": 0,
                "data": {
                    "items": [
                        {"field_name": field_name, "type": 1}
                        for field_name in DEFAULT_FIELD_MAP.values()
                    ]
                },
            }
        if url.endswith("/records/batch_create"):
            records = (payload or {}).get("records") or []
            return {
                "code": 0,
                "data": {
                    "records": [
                        {"record_id": f"rec-{index}"}
                        for index, _record in enumerate(records, start=1)
                    ]
                },
            }
        return {"code": 0}


class FakeClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.rows: list[dict] = []
        self.webhooks: list[dict] = []

    def batch_create_records(self, rows):
        if self.fail:
            raise FeishuError("temporary unavailable")
        self.rows.extend(rows)
        return [f"rec-{len(self.rows)}" for _row in rows]

    def send_webhook(self, **values):
        self.webhooks.append(values)


def config() -> FeishuConfig:
    return FeishuConfig(
        app_id="cli_app",
        app_secret="secret",
        app_token="app_token",
        table_id="table_id",
        public_base_url="https://bids.example.internal",
    )


def workflow_result() -> dict:
    return {
        "status": "completed",
        "changes": [{"project_id": "project-1", "type": "new_project"}],
        "projects": [{
            "project_id": "project-1",
            "title": "服务器采购项目",
            "documents": [{
                "notice": {
                    "title": "服务器采购项目招标公告",
                    "published_at": "2026-07-18T09:00:00+08:00",
                    "core_content": "采购服务器十台，投标截止日期见公告。",
                    "source": {
                        "source_name": "中国政府采购网",
                        "source_url": "https://example.test/notice/1",
                        "authority": 5,
                    },
                }
            }],
        }],
        "report": {
            "status": "generated",
            "delivery_fingerprint": "delivery-1",
            "documents": [{
                "project_id": "project-1",
                "download_url": "/api/reports/delivery-1/documents/doc-1/download",
            }],
        },
    }


class FeishuClientTest(unittest.TestCase):
    def test_token_is_cached_and_rows_are_mapped_to_bitable_fields(self) -> None:
        transport = FakeTransport()
        client = FeishuBitableClient(config(), transport=transport, clock=lambda: 100.0)

        record_ids = client.batch_create_records([{
            "title": "服务器采购项目",
            "source_url": "https://example.test/notice/1",
            "word_url": "https://bids.example.internal/report.docx",
        }])
        client.batch_create_records([{"title": "第二个项目"}])

        self.assertEqual(record_ids, ["rec-1"])
        token_calls = [call for call in transport.calls if call["url"].endswith("/tenant_access_token/internal")]
        self.assertEqual(len(token_calls), 1)
        create_call = next(call for call in transport.calls if call["url"].endswith("/records/batch_create"))
        self.assertEqual(
            create_call["payload"]["records"][0]["fields"]["项目标题"],
            "服务器采购项目",
        )

    def test_missing_bitable_fields_are_reported_before_writing(self) -> None:
        transport = FakeTransport()
        client = FeishuBitableClient(config(), transport=transport)
        transport.request = lambda *args, **kwargs: (
            {"code": 0, "tenant_access_token": "token", "expire": 7200}
            if str(args[1]).endswith("/tenant_access_token/internal")
            else {"code": 0, "data": {"items": [{"field_name": "项目标题"}]}}
        )

        with self.assertRaisesRegex(FeishuError, "missing required fields"):
            client.batch_create_records([{"title": "项目"}])


class FeishuOutboxTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database_patch = patch.object(database_module, "DATABASE_PATH", self.root / "app.db")
        self.data_patch = patch.object(database_module, "DATA_DIR", self.root)
        self.database_patch.start()
        self.data_patch.start()
        self.now = datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)
        self.repository = Repository()

    def tearDown(self) -> None:
        self.data_patch.stop()
        self.database_patch.stop()
        self.temporary_directory.cleanup()

    def _complete_schedule_with_events(self, service: FeishuDeliveryService) -> None:
        task_id = str(uuid4())
        self.repository.create_subscription(
            task_id=task_id,
            query="查询服务器采购",
            frequency="daily",
            timezone_name="Asia/Shanghai",
            local_time="09:00",
            weekly_day=None,
            run_at=None,
            next_run_at=self.now,
            now=self.now,
            max_retries=3,
            retry_backoff_seconds=30,
        )
        claimed = self.repository.claim_due_subscription(
            worker_id="scheduler-1",
            now=self.now,
            lease_duration=timedelta(minutes=5),
        )
        events = service.prepare_events(
            result=workflow_result(),
            task_id=task_id,
            run_id=claimed["run_id"],
            query="查询服务器采购",
            collected_at=self.now,
        )
        self.assertEqual(len(events), 1)
        self.repository.complete_schedule_run(
            task_id=task_id,
            run_id=claimed["run_id"],
            worker_id="scheduler-1",
            now=self.now,
            next_run_at=self.now + timedelta(days=1),
            external_events=events,
        )

    def test_successful_delivery_is_persisted_and_idempotent(self) -> None:
        client = FakeClient()
        service = FeishuDeliveryService(
            self.repository,
            config=config(),
            client=client,
            worker_id="feishu-1",
            now=lambda: self.now,
        )
        self._complete_schedule_with_events(service)

        first = service.flush_due()
        second = service.flush_due()

        self.assertEqual(first["delivered"], 1)
        self.assertEqual(second["delivered"], 0)
        self.assertEqual(len(client.rows), 1)
        self.assertEqual(client.rows[0]["word_url"], "https://bids.example.internal/api/reports/delivery-1/documents/doc-1/download")
        outbox = self.repository.list_external_deliveries(provider=PROVIDER_ID)
        self.assertEqual(outbox[0]["status"], "delivered")

    def test_failed_delivery_returns_to_pending_with_backoff(self) -> None:
        service = FeishuDeliveryService(
            self.repository,
            config=config(),
            client=FakeClient(fail=True),
            worker_id="feishu-1",
            now=lambda: self.now,
        )
        self._complete_schedule_with_events(service)

        result = service.flush_due()

        self.assertEqual(result["failed"], 1)
        outbox = self.repository.list_external_deliveries(provider=PROVIDER_ID)
        self.assertEqual(outbox[0]["status"], "pending")
        self.assertEqual(outbox[0]["attempts"], 1)
        self.assertIn("temporary unavailable", outbox[0]["last_error"])

    def test_no_change_run_creates_no_external_event(self) -> None:
        service = FeishuDeliveryService(self.repository, config=config(), client=FakeClient())
        result = workflow_result()
        result["changes"] = []
        result["report"] = {"status": "no_change"}

        events = service.prepare_events(
            result=result,
            task_id="task",
            run_id="run",
            query="查询服务器采购",
            collected_at=self.now,
        )

        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
