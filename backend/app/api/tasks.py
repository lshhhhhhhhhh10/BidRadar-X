from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, HTTPException

from .projects import build_source_project_profiles
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
    if state["status"] != "completed":
        raise HTTPException(
            status_code=502,
            detail={
                "code": "task_failed",
                "message": "任务执行失败，请稍后重试或在报告历史中查看状态。",
            },
        )
    Repository().save_project_profiles(
        state["run_id"],
        build_source_project_profiles(state),
    )
    return {
        "task_id": state["task_id"],
        "run_id": state["run_id"],
        "status": state["status"],
        "task_spec": state["task_spec"],
        "selected_sources": _sanitize_error_details(state["selected_sources"]),
        "steps": state["steps"],
        "funnel": state["funnel"],
        "projects": state["projects"],
        "changes": state["changes"],
        "quality_passed": state["quality_passed"],
        "quality_issues": state["quality_issues"],
        "report": _sanitize_error_details(state["report"]),
    }


@router.get("/runs")
def list_runs() -> dict[str, list[dict]]:
    return {"items": [_run_summary(run) for run in Repository().list_runs()]}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = Repository().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return _run_summary(run)


def _run_summary(run: dict) -> dict:
    return {
        "task_id": run["task_id"],
        "run_id": run["run_id"],
        "query": run.get("query", ""),
        "frequency": run.get("frequency", "once"),
        "status": run["status"],
        "project_count": len(run.get("projects", [])),
    }


def _sanitize_error_details(value: object) -> object:
    if isinstance(value, list):
        return [_sanitize_error_details(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: (
            "来源采集失败，请稍后重试。"
            if key == "error"
            else _sanitize_error_details(item)
        )
        for key, item in value.items()
    }
