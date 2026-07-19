from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from threading import Event
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import APIRouter, HTTPException

from .projects import build_source_project_summaries
from ..schemas.task import TaskRunRequest, TaskRunResponse
from ..services.task_runner import TaskRunner
from ..services.live_progress import build_live_progress
from ..services.schedule_intent import ScheduleIntentError, ScheduleIntentParser
from ..services.scheduler import LocalScheduler, SubscriptionService, SystemClock
from ..services.source_failures import source_failure_reason
from ..storage.repository import Repository
from ..workflow.graph import WORKFLOW_DEFINITION
from ..ai import AICoordinator


router = APIRouter(prefix="/api", tags=["tasks"])

_LIVE_JOBS: dict[str, dict] = {}
_LIVE_TASKS: set[asyncio.Task] = set()


class LiveTaskPaused(RuntimeError):
    """Raised cooperatively between workflow nodes after a pause request."""


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "local-prototype"}


@router.get("/workflow")
def workflow_definition() -> dict[str, list[str]]:
    return {"nodes": WORKFLOW_DEFINITION}


@router.post("/tasks/run", response_model=TaskRunResponse)
async def run_task(request: TaskRunRequest) -> dict:
    task_id = _task_id(request)
    state = await TaskRunner().run(
        task_id=task_id,
        query=request.query,
        frequency=request.frequency,
        interval_minutes=request.interval_minutes,
        requested_subject=request.subject,
        requested_region=request.region,
    )
    if state["status"] != "completed":
        raise HTTPException(
            status_code=502,
            detail={
                "code": "task_failed",
                "message": _workflow_failure_message(state),
            },
        )
    Repository().save_project_profiles(
        state["run_id"],
        build_source_project_summaries(state),
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
        "ai": {
            **AICoordinator.status(),
            "calls": state.get("ai_audit", []),
        },
        "report": _sanitize_error_details(state["report"]),
    }


@router.post("/tasks/live", status_code=202)
async def start_live_task(request: TaskRunRequest) -> dict:
    """Start a workflow and expose real node-by-node progress for the UI."""

    _prune_live_jobs()
    job_id = str(uuid4())
    run_id = str(uuid4())
    task_id = _task_id(request)
    job = {
        "job_id": job_id,
        "run_id": run_id,
        "task_id": task_id,
        "state": {
            "run_id": run_id,
            "task_id": task_id,
            "query": request.query,
            "frequency": request.frequency,
            "interval_minutes": request.interval_minutes,
        },
        "lifecycle": "running",
        "error_message": None,
        "pause_event": Event(),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    _LIVE_JOBS[job_id] = job
    task = asyncio.create_task(_execute_live_task(job, request))
    _LIVE_TASKS.add(task)
    task.add_done_callback(_LIVE_TASKS.discard)
    return _public_live_job(job)


@router.get("/tasks/live/{job_id}")
def get_live_task(job_id: str) -> dict:
    job = _LIVE_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="live task not found")
    return _public_live_job(job)


@router.post("/tasks/live/{job_id}/pause")
def pause_live_task(job_id: str) -> dict:
    job = _LIVE_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="live task not found")
    if job["lifecycle"] in {"completed", "empty", "failed", "paused"}:
        return _public_live_job(job)
    job["pause_event"].set()
    job["lifecycle"] = "pausing"
    job["error_message"] = "已请求暂停；当前步骤结束后将安全停止，不会生成或跳转到项目报告。"
    job["updated_at"] = datetime.now(timezone.utc)
    return _public_live_job(job)


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


def _task_id(request: TaskRunRequest) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            "|".join(
                (
                    request.query,
                    request.frequency,
                    str(request.interval_minutes or ""),
                    request.subject or "",
                    request.region or "",
                )
            ),
        )
    )


async def _execute_live_task(job: dict, request: TaskRunRequest) -> None:
    async def update(state: dict) -> None:
        job["state"] = state
        job["updated_at"] = datetime.now(timezone.utc)
        if job["pause_event"].is_set():
            raise LiveTaskPaused

    try:
        async def run_workflow() -> dict:
            return await TaskRunner().run(
                task_id=job["task_id"],
                run_id=job["run_id"],
                query=request.query,
                frequency=request.frequency,
                interval_minutes=request.interval_minutes,
                requested_subject=request.subject,
                requested_region=request.region,
                progress_callback=update,
            )

        # Workflow nodes include network and document operations. Isolating the
        # graph on a worker thread keeps polling and the rest of the local API
        # responsive while those blocking operations are in flight.
        state = await asyncio.to_thread(lambda: asyncio.run(run_workflow()))
        if state.get("status") == "completed":
            repository = Repository()
            repository.save_project_profiles(
                state["run_id"],
                build_source_project_summaries(state),
            )
            subscription = _ensure_recurring_subscription(
                repository=repository,
                task_id=job["task_id"],
                request=request,
            )
            if subscription is not None:
                job["subscription"] = subscription
            job["lifecycle"] = "completed" if state.get("projects") else "empty"
        else:
            job["lifecycle"] = "failed"
            job["error_message"] = _workflow_failure_message(state)
        job["state"] = state
    except LiveTaskPaused:
        job["lifecycle"] = "paused"
        job["error_message"] = "任务已暂停，后续步骤未执行，也没有生成或跳转到项目报告。"
    except Exception as error:
        job["lifecycle"] = "failed"
        job["error_message"] = (
            "检索链路执行异常，已终止且未写入项目报告："
            f"{source_failure_reason({'error_type': type(error).__name__, 'error': str(error)})}"
        )
    finally:
        job["updated_at"] = datetime.now(timezone.utc)


def _public_live_job(job: dict) -> dict:
    progress = build_live_progress(
        job.get("state", {}),
        lifecycle=job["lifecycle"],
        error_message=job.get("error_message"),
    )
    return {
        "job_id": job["job_id"],
        **progress,
        "subscription": job.get("subscription"),
        "updated_at": job["updated_at"].isoformat(),
        "redirect_url": (
            f"/reports?run_id={job['run_id']}"
            if job["lifecycle"] == "completed" and progress["project_count"] > 0
            else None
        ),
    }


def _workflow_failure_message(state: dict) -> str:
    failed_sources = [
        item
        for item in state.get("selected_sources", [])
        if item.get("collection_status") == "failed"
    ]
    if failed_sources:
        reasons: list[str] = []
        for item in failed_sources[:4]:
            reason = item.get("failure_reason") or source_failure_reason(item)
            reasons.append(f"{item.get('name') or item.get('source_id')}：{reason}")
        return "信息源采集失败，链路已停止。" + "；".join(reasons)
    issues = [str(item) for item in state.get("quality_issues", []) if item]
    if issues:
        return f"检索链路未通过事实审核：{issues[0]}"
    return "检索链路未完整执行，已停止后续步骤。"


def _ensure_recurring_subscription(
    *,
    repository: Repository,
    task_id: str,
    request: TaskRunRequest,
) -> dict | None:
    if request.frequency not in {"interval", "daily", "weekly"}:
        return None
    clock = SystemClock()
    query = request.query
    local_time = "09:00"
    weekly_day = "monday" if request.frequency == "weekly" else None
    interval_minutes = request.interval_minutes
    try:
        intent = ScheduleIntentParser().parse(
            request.query,
            timezone="Asia/Shanghai",
            now=clock.now(),
        )
        if intent.frequency == request.frequency:
            query = intent.search_query
            local_time = intent.local_time
            weekly_day = intent.weekly_day
            interval_minutes = intent.interval_minutes
    except ScheduleIntentError:
        # A cadence without an explicit clock still becomes reliable: daily
        # defaults to 09:00, weekly defaults to Monday 09:00 (Shanghai time).
        pass

    service = SubscriptionService(
        repository=repository,
        scheduler=LocalScheduler(clock=clock),
        clock=clock,
    )
    return service.create(
        task_id=task_id,
        query=query,
        frequency=request.frequency,
        interval_minutes=interval_minutes,
        timezone_name="Asia/Shanghai",
        local_time=local_time,
        weekly_day=weekly_day,
        run_at=None,
        max_retries=3,
        retry_backoff_seconds=30,
    )


def _prune_live_jobs() -> None:
    if len(_LIVE_JOBS) < 100:
        return
    finished = sorted(
        (item for item in _LIVE_JOBS.values() if item["lifecycle"] != "running"),
        key=lambda item: item["updated_at"],
    )
    for item in finished[: max(1, len(_LIVE_JOBS) - 80)]:
        _LIVE_JOBS.pop(item["job_id"], None)
