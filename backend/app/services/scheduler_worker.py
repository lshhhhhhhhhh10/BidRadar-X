from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any, cast
from uuid import uuid4

from ..integrations.feishu import FeishuDeliveryService
from .scheduler import Clock, LocalScheduler


LOGGER = logging.getLogger(__name__)


class _DisabledExternalDelivery:
    """Fail-closed adapter used when an optional delivery channel is misconfigured."""

    def prepare_events(self, **_values: Any) -> list[dict[str, Any]]:
        return []

    def flush_due(self) -> dict[str, Any]:
        return {"status": "disabled", "delivered": 0}


class SchedulerWorker:
    def __init__(
        self,
        *,
        repository: Any,
        task_runner: Any,
        scheduler: LocalScheduler,
        clock: Clock,
        worker_id: str | None = None,
        lease_duration: timedelta = timedelta(minutes=5),
        poll_interval_seconds: float = 1.0,
        external_delivery: Any | None = None,
    ) -> None:
        self.repository = repository
        self.task_runner = task_runner
        self.scheduler = scheduler
        self.clock = clock
        self.worker_id = worker_id or f"scheduler-{uuid4()}"
        self.lease_duration = lease_duration
        self.poll_interval_seconds = poll_interval_seconds
        if external_delivery is not None:
            self.external_delivery = external_delivery
        else:
            try:
                self.external_delivery = FeishuDeliveryService(repository)
            except Exception as error:
                # Feishu is an optional downstream delivery channel. Invalid
                # credentials or malformed environment settings must not stop
                # the scheduler from collecting and publishing local reports.
                LOGGER.warning("External delivery is disabled: %s", error)
                self.external_delivery = _DisabledExternalDelivery()
        self._stop = asyncio.Event()

    async def run_once(self) -> bool:
        await self._flush_external_deliveries()
        claimed = self.repository.claim_due_subscription(
            worker_id=self.worker_id,
            now=self.clock.now(),
            lease_duration=self.lease_duration,
        )
        if claimed is None:
            return False

        heartbeat_stop = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(claimed["task_id"], heartbeat_stop))
        workflow_task = asyncio.create_task(self._invoke_claimed(claimed))
        try:
            completed, _pending = await asyncio.wait(
                {workflow_task, heartbeat},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat in completed and not heartbeat.result():
                workflow_task.cancel()
                await asyncio.gather(workflow_task, return_exceptions=True)
                self._record_failure(claimed, RuntimeError("scheduler lease was lost"))
                return True
            result = workflow_task.result()
        except Exception as error:
            self._record_failure(claimed, error)
        else:
            next_run_at = self._next_recurring_run(claimed)
            try:
                external_events = self.external_delivery.prepare_events(
                    result=result,
                    task_id=claimed["task_id"],
                    run_id=claimed["run_id"],
                    query=claimed["query"],
                    collected_at=self.clock.now(),
                )
            except Exception as error:
                # The workflow result is already valid at this point. Keep the
                # scheduled run successful and let an external-channel repair
                # be handled independently instead of replaying the crawl.
                LOGGER.warning("External delivery event preparation failed: %s", error)
                external_events = []
            completed = self.repository.complete_schedule_run(
                task_id=claimed["task_id"],
                run_id=claimed["run_id"],
                worker_id=self.worker_id,
                now=self.clock.now(),
                next_run_at=next_run_at,
                external_events=external_events,
            )
            if completed:
                await self._flush_external_deliveries()
        finally:
            heartbeat_stop.set()
            if not heartbeat.done():
                await heartbeat
            if not workflow_task.done():
                workflow_task.cancel()
                await asyncio.gather(workflow_task, return_exceptions=True)
        return True

    def run_once_sync(self) -> bool:
        return asyncio.run(self.run_once())

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            worked = await self.run_once()
            if worked:
                continue
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.poll_interval_seconds,
                )
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()

    def _next_recurring_run(self, claimed: dict[str, Any]) -> datetime | None:
        if claimed["frequency"] == "once":
            return None
        return cast(datetime, self.scheduler.next_run_at(
            frequency=claimed["frequency"],
            interval_minutes=claimed.get("interval_minutes"),
            timezone_name=claimed["timezone"],
            local_time=claimed["local_time"],
            weekly_day=claimed["weekly_day"],
            after=self.clock.now(),
        ))

    async def _invoke_claimed(self, claimed: dict[str, Any]) -> dict[str, Any]:
        result = await self.task_runner.run(
            task_id=claimed["task_id"],
            query=claimed["query"],
            frequency=claimed["frequency"],
            interval_minutes=claimed.get("interval_minutes"),
            run_id=claimed["run_id"],
        )
        if result.get("status") == "failed":
            report = result.get("report", {})
            raise RuntimeError(
                report.get("error")
                or report.get("error_type")
                or "workflow returned failed status"
            )
        return result

    async def _flush_external_deliveries(self) -> None:
        try:
            await asyncio.to_thread(self.external_delivery.flush_due)
        except Exception:
            # External delivery has its own persisted retry state and must never
            # turn a completed crawl into a failed workflow run.
            return

    def _record_failure(self, claimed: dict[str, Any], error: Exception) -> None:
        error_text = f"{type(error).__name__}: {error}"
        updated = self.repository.fail_schedule_run(
            task_id=claimed["task_id"],
            run_id=claimed["run_id"],
            worker_id=self.worker_id,
            now=self.clock.now(),
            error=error_text,
        )
        if not updated:
            self.repository.mark_schedule_run_failed(
                task_id=claimed["task_id"],
                run_id=claimed["run_id"],
                now=self.clock.now(),
                error=error_text,
            )

    async def _heartbeat(self, task_id: str, stop: asyncio.Event) -> bool:
        interval = max(self.lease_duration.total_seconds() / 3, 0.1)
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except TimeoutError:
                try:
                    renewed = self.repository.renew_subscription_lease(
                        task_id=task_id,
                        worker_id=self.worker_id,
                        now=self.clock.now(),
                        lease_duration=self.lease_duration,
                    )
                except Exception:
                    return False
                if not renewed:
                    return False
        return True
