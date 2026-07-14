from __future__ import annotations

from typing import Any
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
        run_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = run_id or str(uuid4())
        self.repository.create_task(task_id, query, frequency)
        initial_state = {
            "task_id": task_id,
            "run_id": run_id,
            "query": query,
            "frequency": frequency,
            "status": "running",
            "steps": [],
            "funnel": {},
            "retry_count": 0,
            "quality_passed": False,
            "quality_issues": [],
        }
        state = await self.workflow.ainvoke(
            initial_state,
            config={"recursion_limit": 50},
        )
        self.repository.save_run(state)
        return state
