from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter

from ..schemas.task import TaskRunRequest, TaskRunResponse
from ..services.task_runner import TaskRunner
from ..storage.repository import Repository
from ..workflow.graph import WORKFLOW_DEFINITION


router = APIRouter(prefix="/api", tags=["tasks"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "local-prototype"}


@router.get("/workflow")
def workflow_definition() -> dict[str, list[str]]:
    return {"nodes": WORKFLOW_DEFINITION}


@router.post("/tasks/run", response_model=TaskRunResponse)
async def run_task(request: TaskRunRequest) -> dict:
    task_id = str(uuid5(NAMESPACE_URL, f"{request.query}|{request.frequency}"))
    state = await TaskRunner().run(
        task_id=task_id,
        query=request.query,
        frequency=request.frequency,
    )
    return {
        "task_id": state["task_id"],
        "run_id": state["run_id"],
        "status": state["status"],
        "task_spec": state["task_spec"],
        "selected_sources": state["selected_sources"],
        "steps": state["steps"],
        "funnel": state["funnel"],
        "projects": state["projects"],
        "changes": state["changes"],
        "quality_passed": state["quality_passed"],
        "quality_issues": state["quality_issues"],
        "report": state["report"],
    }


@router.get("/runs")
def list_runs() -> dict[str, list[dict]]:
    return {"items": Repository().list_runs()}
