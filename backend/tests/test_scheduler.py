from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.services.scheduler import LocalScheduler, SubscriptionService
from app.services.scheduler_worker import SchedulerWorker
from app.services.task_runner import TaskRunner
from app.services import publisher as publisher_module
from app.services.publisher import Publisher
from app.storage import database as database_module
from app.storage.repository import Repository
from app.workflow.nodes import source_select
from tests.integration_support import isolated_source_set


class FakeClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        return self.current

    def advance_to(self, value: datetime) -> None:
        self.current = value


class RecordingTaskRunner:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[dict] = []

    async def run(self, **values) -> dict:
        self.calls.append(values)
        if self.failures:
            self.failures -= 1
            raise RuntimeError("workflow unavailable")
        return {"status": "completed", "report": {"status": "no_change"}}


class CancelOnLeaseLossRunner:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self.cancelled = False

    async def run(self, **values) -> dict:
        self.repository.delete_subscription(values["task_id"])
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return {"status": "completed"}


class ScheduleCalculationTest(unittest.TestCase):
    def test_asia_shanghai_daily_nine_uses_the_next_local_occurrence(self) -> None:
        clock = FakeClock(datetime(2026, 7, 14, 0, 30, tzinfo=timezone.utc))
        scheduler = LocalScheduler(clock=clock)

        next_run = scheduler.next_run_at(
            frequency="daily",
            timezone_name="Asia/Shanghai",
            local_time="09:00",
        )

        self.assertEqual(next_run, datetime(2026, 7, 14, 1, 0, tzinfo=timezone.utc))

    def test_weekly_schedule_uses_the_requested_local_weekday_and_time(self) -> None:
        clock = FakeClock(datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc))
        scheduler = LocalScheduler(clock=clock)

        next_run = scheduler.next_run_at(
            frequency="weekly",
            timezone_name="Asia/Shanghai",
            local_time="09:00",
            weekly_day="monday",
        )

        self.assertEqual(next_run, datetime(2026, 7, 20, 1, 0, tzinfo=timezone.utc))

    def test_once_schedule_preserves_an_explicit_future_instant(self) -> None:
        clock = FakeClock(datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc))
        scheduler = LocalScheduler(clock=clock)
        run_at = datetime(2026, 7, 14, 2, 2, tzinfo=timezone.utc)

        self.assertEqual(
            scheduler.next_run_at(
                frequency="once",
                timezone_name="Asia/Shanghai",
                local_time="10:02",
                run_at=run_at,
            ),
            run_at,
        )

    def test_nonexistent_dst_wall_time_moves_to_the_first_valid_local_time(self) -> None:
        clock = FakeClock(datetime(2026, 3, 8, 5, 0, tzinfo=timezone.utc))

        next_run = LocalScheduler(clock=clock).next_run_at(
            frequency="daily",
            timezone_name="America/New_York",
            local_time="02:30",
        )

        self.assertEqual(next_run, datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc))

    def test_ambiguous_dst_wall_time_uses_the_first_occurrence_only(self) -> None:
        clock = FakeClock(datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc))

        next_run = LocalScheduler(clock=clock).next_run_at(
            frequency="daily",
            timezone_name="America/New_York",
            local_time="01:30",
        )

        self.assertEqual(next_run, datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc))


class PersistentClaimTest(unittest.TestCase):
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
        self.clock = FakeClock(datetime(2026, 7, 14, 1, 0, tzinfo=timezone.utc))

    def tearDown(self) -> None:
        self.data_patch.stop()
        self.database_patch.stop()
        self.temporary_directory.cleanup()

    def create_due_subscription(self) -> str:
        task_id = str(uuid4())
        Repository().create_subscription(
            task_id=task_id,
            query="查询服务器采购公告",
            frequency="daily",
            timezone_name="Asia/Shanghai",
            local_time="09:00",
            weekly_day=None,
            run_at=None,
            next_run_at=self.clock.now(),
            now=self.clock.now(),
            max_retries=2,
            retry_backoff_seconds=30,
        )
        return task_id

    def test_subscription_survives_repository_restart(self) -> None:
        task_id = self.create_due_subscription()

        restored = Repository().get_subscription(task_id)

        self.assertIsNotNone(restored)
        self.assertEqual(restored["task_id"], task_id)
        self.assertEqual(restored["next_run_at"], "2026-07-14T01:00:00+00:00")
        self.assertEqual(restored["status"], "active")

    def test_restarted_worker_executes_a_persisted_due_subscription(self) -> None:
        task_id = self.create_due_subscription()
        runner = RecordingTaskRunner()
        restarted_worker = SchedulerWorker(
            repository=Repository(),
            task_runner=runner,
            scheduler=LocalScheduler(clock=self.clock),
            clock=self.clock,
            worker_id="restarted-worker",
        )

        self.assertTrue(restarted_worker.run_once_sync())

        restored = Repository().get_subscription(task_id)
        self.assertEqual(restored["last_run_at"], "2026-07-14T01:00:00+00:00")
        self.assertEqual(len(runner.calls), 1)

    def test_two_workers_cannot_claim_the_same_due_task(self) -> None:
        task_id = self.create_due_subscription()

        def claim(worker_id: str):
            return Repository().claim_due_subscription(
                worker_id=worker_id,
                now=self.clock.now(),
                lease_duration=timedelta(minutes=5),
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim, ["worker-a", "worker-b"]))

        winners = [item for item in results if item is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0]["task_id"], task_id)

    def test_expired_lease_recovers_a_task_after_worker_crash(self) -> None:
        task_id = self.create_due_subscription()
        repository = Repository()
        first = repository.claim_due_subscription(
            worker_id="worker-a",
            now=self.clock.now(),
            lease_duration=timedelta(minutes=5),
        )

        self.clock.advance_to(self.clock.now() + timedelta(minutes=4, seconds=59))
        self.assertIsNone(
            repository.claim_due_subscription(
                worker_id="worker-b",
                now=self.clock.now(),
                lease_duration=timedelta(minutes=5),
            )
        )

        self.clock.advance_to(self.clock.now() + timedelta(seconds=2))
        recovered = repository.claim_due_subscription(
            worker_id="worker-b",
            now=self.clock.now(),
            lease_duration=timedelta(minutes=5),
        )

        self.assertEqual(recovered["task_id"], task_id)
        self.assertNotEqual(recovered["run_id"], first["run_id"])
        attempts = repository.list_schedule_runs(task_id)
        self.assertEqual([item["status"] for item in attempts], ["lease_expired", "running"])

    def test_once_success_marks_subscription_completed(self) -> None:
        task_id = str(uuid4())
        repository = Repository()
        repository.create_subscription(
            task_id=task_id,
            query="查询交换机采购公告",
            frequency="once",
            timezone_name="Asia/Shanghai",
            local_time="09:00",
            weekly_day=None,
            run_at=self.clock.now(),
            next_run_at=self.clock.now(),
            now=self.clock.now(),
            max_retries=2,
            retry_backoff_seconds=30,
        )
        runner = RecordingTaskRunner()
        worker = SchedulerWorker(
            repository=repository,
            task_runner=runner,
            scheduler=LocalScheduler(clock=self.clock),
            clock=self.clock,
            worker_id="worker-a",
        )

        self.assertTrue(worker.run_once_sync())

        restored = repository.get_subscription(task_id)
        self.assertEqual(restored["status"], "completed")
        self.assertIsNone(restored["lease_owner"])
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(repository.list_schedule_runs(task_id)[0]["status"], "succeeded")

    def test_pause_prevents_execution_and_resume_recalculates_next_time(self) -> None:
        task_id = self.create_due_subscription()
        repository = Repository()
        service = SubscriptionService(
            repository=repository,
            scheduler=LocalScheduler(clock=self.clock),
            clock=self.clock,
        )
        runner = RecordingTaskRunner()
        worker = SchedulerWorker(
            repository=repository,
            task_runner=runner,
            scheduler=LocalScheduler(clock=self.clock),
            clock=self.clock,
            worker_id="worker-a",
        )

        service.pause(task_id)
        self.assertFalse(worker.run_once_sync())
        self.assertEqual(runner.calls, [])

        resumed = service.resume(task_id)
        self.assertEqual(resumed["status"], "active")
        self.assertEqual(resumed["next_run_at"], "2026-07-15T01:00:00+00:00")
        self.clock.advance_to(datetime(2026, 7, 15, 1, 0, tzinfo=timezone.utc))
        self.assertTrue(worker.run_once_sync())

    def test_workflow_failure_retries_with_backoff_then_succeeds(self) -> None:
        task_id = self.create_due_subscription()
        repository = Repository()
        runner = RecordingTaskRunner(failures=1)
        worker = SchedulerWorker(
            repository=repository,
            task_runner=runner,
            scheduler=LocalScheduler(clock=self.clock),
            clock=self.clock,
            worker_id="worker-a",
        )

        self.assertTrue(worker.run_once_sync())
        failed = repository.get_subscription(task_id)
        self.assertEqual(failed["status"], "active")
        self.assertEqual(failed["retry_count"], 1)
        self.assertEqual(failed["next_run_at"], "2026-07-14T01:00:30+00:00")
        self.assertIn("workflow unavailable", failed["last_error"])

        self.assertFalse(worker.run_once_sync())
        self.clock.advance_to(datetime(2026, 7, 14, 1, 0, 30, tzinfo=timezone.utc))
        self.assertTrue(worker.run_once_sync())
        succeeded = repository.get_subscription(task_id)
        self.assertEqual(succeeded["retry_count"], 0)
        self.assertEqual(succeeded["next_run_at"], "2026-07-15T01:00:00+00:00")
        self.assertEqual(
            [item["status"] for item in repository.list_schedule_runs(task_id)],
            ["failed", "succeeded"],
        )

    def test_retry_limit_marks_a_permanently_failing_task_failed(self) -> None:
        task_id = str(uuid4())
        repository = Repository()
        repository.create_subscription(
            task_id=task_id,
            query="查询服务器采购公告",
            frequency="once",
            timezone_name="Asia/Shanghai",
            local_time="09:00",
            weekly_day=None,
            run_at=self.clock.now(),
            next_run_at=self.clock.now(),
            now=self.clock.now(),
            max_retries=1,
            retry_backoff_seconds=10,
        )
        worker = SchedulerWorker(
            repository=repository,
            task_runner=RecordingTaskRunner(failures=2),
            scheduler=LocalScheduler(clock=self.clock),
            clock=self.clock,
            worker_id="worker-a",
        )

        self.assertTrue(worker.run_once_sync())
        self.clock.advance_to(self.clock.now() + timedelta(seconds=10))
        self.assertTrue(worker.run_once_sync())

        failed = repository.get_subscription(task_id)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["retry_count"], 2)
        self.clock.advance_to(self.clock.now() + timedelta(days=1))
        self.assertFalse(worker.run_once_sync())

    def test_worker_cancels_its_workflow_when_the_lease_is_lost(self) -> None:
        task_id = self.create_due_subscription()
        repository = Repository()
        runner = CancelOnLeaseLossRunner(repository)
        worker = SchedulerWorker(
            repository=repository,
            task_runner=runner,
            scheduler=LocalScheduler(clock=self.clock),
            clock=self.clock,
            worker_id="worker-a",
            lease_duration=timedelta(milliseconds=150),
        )

        self.assertTrue(worker.run_once_sync())

        self.assertTrue(runner.cancelled)
        self.assertIsNone(repository.get_subscription(task_id))
        self.assertEqual(repository.list_schedule_runs(task_id)[0]["status"], "failed")


class ScheduledWorkflowIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.report_dir = self.root / "reports"
        self.patches = [
            patch.object(database_module, "DATABASE_PATH", self.root / "app.db"),
            patch.object(database_module, "DATA_DIR", self.root),
            patch.object(publisher_module, "REPORT_DIR", self.report_dir),
        ]
        for active_patch in self.patches:
            active_patch.start()
        self.clock = FakeClock(datetime(2026, 7, 14, 1, 0, tzinfo=timezone.utc))
        self.repository = Repository()
        self.task_id = str(uuid4())
        self.repository.create_subscription(
            task_id=self.task_id,
            query="查询 2026-07-14 全国服务器采购公告",
            frequency="daily",
            timezone_name="Asia/Shanghai",
            local_time="09:00",
            weekly_day=None,
            run_at=None,
            next_run_at=self.clock.now(),
            now=self.clock.now(),
            max_retries=2,
            retry_backoff_seconds=30,
        )

    def tearDown(self) -> None:
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temporary_directory.cleanup()

    def worker(self) -> SchedulerWorker:
        return SchedulerWorker(
            repository=self.repository,
            task_runner=TaskRunner(repository=self.repository),
            scheduler=LocalScheduler(clock=self.clock),
            clock=self.clock,
            worker_id="integration-worker",
        )

    def test_failed_delivery_preserves_incremental_state_and_retry_commits_it(self) -> None:
        worker = self.worker()
        with (
            patch.object(source_select, "SOURCE_ADAPTERS", isolated_source_set()),
            patch.object(Publisher, "_publish_delivery_report", side_effect=RuntimeError("docx failed")),
        ):
            self.assertTrue(worker.run_once_sync())

        failed = self.repository.get_subscription(self.task_id)
        self.assertEqual(failed["status"], "active")
        self.assertEqual(failed["retry_count"], 1)
        self.assertEqual(self.repository.load_project_snapshots(self.task_id), {})
        self.assertEqual(self.repository.load_watermarks(self.task_id), {})

        self.clock.advance_to(self.clock.now() + timedelta(seconds=30))
        with patch.object(source_select, "SOURCE_ADAPTERS", isolated_source_set()):
            self.assertTrue(worker.run_once_sync())

        recovered = self.repository.get_subscription(self.task_id)
        self.assertEqual(recovered["retry_count"], 0)
        self.assertEqual(len(self.repository.load_project_snapshots(self.task_id)), 1)
        self.assertEqual(len(self.repository.load_watermarks(self.task_id)), 2)
        self.assertEqual(self.repository.list_deliveries(self.task_id)[0]["status"], "generated")
        self.assertEqual(len(list(self.report_dir.glob("*.docx"))), 1)

    def test_repeated_scheduled_event_does_not_create_a_duplicate_report(self) -> None:
        worker = self.worker()
        with patch.object(source_select, "SOURCE_ADAPTERS", isolated_source_set()):
            self.assertTrue(worker.run_once_sync())
            self.clock.advance_to(datetime(2026, 7, 15, 1, 0, tzinfo=timezone.utc))
            self.assertTrue(worker.run_once_sync())

        self.assertEqual(len(self.repository.list_deliveries(self.task_id)), 1)
        self.assertEqual(len(list(self.report_dir.glob("*.docx"))), 1)
        self.assertEqual(
            [item["status"] for item in self.repository.list_schedule_runs(self.task_id)],
            ["succeeded", "succeeded"],
        )
        runs = self.repository.list_runs()
        self.assertEqual({run["report"]["status"] for run in runs}, {"generated", "no_change"})


if __name__ == "__main__":
    unittest.main()
