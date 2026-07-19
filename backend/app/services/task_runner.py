from __future__ import annotations

from inspect import isawaitable
from typing import Any, Awaitable, Callable
from uuid import uuid4

from ..storage.repository import Repository
from ..workflow.graph import WORKFLOW


class TaskRunner:
    """The single workflow entry point shared by HTTP and scheduled runs."""

    def __init__(self, *, repository: Repository | None = None, workflow: Any = None) -> None:
        self.repository = repository or Repository()
        self.workflow = workflow or WORKFLOW

    async def run(
        self,
        *,
        task_id: str,
        query: str,
        frequency: str,
        interval_minutes: int | None = None,
        run_id: str | None = None,
        requested_subject: str | None = None,
        requested_region: str | None = None,
        progress_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> dict[str, Any]:
        run_id = run_id or str(uuid4())
        self.repository.create_task(task_id, query, frequency)
        initial_state = {
            "task_id": task_id,
            "run_id": run_id,
            "query": query,
            "frequency": frequency,
            "interval_minutes": interval_minutes,
            "requested_subject": requested_subject,
            "requested_region": requested_region,
            "status": "running",
            "steps": [],
            "funnel": {},
            "retry_count": 0,
            "quality_passed": False,
            "quality_issues": [],
            "ai_audit": [],
        }
        if progress_callback is None:
            state = await self.workflow.ainvoke(
                initial_state,
                config={"recursion_limit": 50},
            )
        else:
            callback_result = progress_callback(initial_state)
            if isawaitable(callback_result):
                await callback_result
            state = initial_state
            async for snapshot in self.workflow.astream(
                initial_state,
                config={"recursion_limit": 50},
                stream_mode="values",
            ):
                state = dict(snapshot)
                callback_result = progress_callback(state)
                if isawaitable(callback_result):
                    await callback_result
        # Keep completed run state for scheduled-trigger auditing. The report
        # history query separately excludes attempts without material changes.
        if state.get("status") == "completed" and state.get("projects"):
            self.repository.save_run(state)
        return state
