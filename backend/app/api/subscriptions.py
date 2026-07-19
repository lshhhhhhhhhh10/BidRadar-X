from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import ValidationError

from ..schemas.task import (
    NaturalLanguageSubscriptionCreateRequest,
    NaturalLanguageSubscriptionCreateResponse,
    SubscriptionCreateRequest,
    SubscriptionDetailResponse,
    SubscriptionListResponse,
    SubscriptionResponse,
)
from ..services.schedule_intent import ScheduleIntentError, ScheduleIntentParser
from ..services.scheduler import LocalScheduler, SubscriptionService, SystemClock
from ..storage.repository import Repository


router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


def _service() -> SubscriptionService:
    clock = SystemClock()
    return SubscriptionService(
        repository=Repository(),
        scheduler=LocalScheduler(clock=clock),
        clock=clock,
    )


def _create_validated_subscription(
    service: SubscriptionService,
    request: SubscriptionCreateRequest,
) -> dict:
    if request.local_time is None:
        raise ValueError("validated subscription request requires local_time")
    return service.create(
        query=request.query,
        frequency=request.frequency,
        interval_minutes=request.interval_minutes,
        timezone_name=request.timezone,
        local_time=request.local_time,
        weekly_day=request.weekly_day,
        run_at=request.run_at,
        max_retries=request.max_retries,
        retry_backoff_seconds=request.retry_backoff_seconds,
    )


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
def create_subscription(request: SubscriptionCreateRequest) -> dict:
    try:
        return _create_validated_subscription(_service(), request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/from-query",
    response_model=NaturalLanguageSubscriptionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_subscription_from_query(
    request: NaturalLanguageSubscriptionCreateRequest,
) -> dict:
    service = _service()
    try:
        intent = ScheduleIntentParser().parse(
            request.query,
            timezone=request.timezone,
            now=service.clock.now(),
        )
        structured = SubscriptionCreateRequest(
            query=intent.search_query,
            frequency=intent.frequency,
            interval_minutes=intent.interval_minutes,
            timezone=intent.timezone,
            local_time=intent.local_time,
            weekly_day=intent.weekly_day,
            run_at=intent.run_at,
            max_retries=request.max_retries,
            retry_backoff_seconds=request.retry_backoff_seconds,
        )
        subscription = _create_validated_subscription(service, structured)
    except ScheduleIntentError as error:
        raise HTTPException(
            status_code=422,
            detail={"code": error.code, "message": error.message},
        ) from error
    except (ValidationError, ValueError) as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "schedule_invalid", "message": str(error)},
        ) from error

    return {
        "subscription": subscription,
        "parsed": {
            "frequency": intent.frequency,
            "interval_minutes": intent.interval_minutes,
            "timezone": intent.timezone,
            "local_time": intent.local_time,
            "weekly_day": intent.weekly_day,
            "run_at": intent.run_at,
            "search_query": intent.search_query,
            "matched_text": intent.matched_text,
        },
    }


@router.get("", response_model=SubscriptionListResponse)
def list_subscriptions() -> dict:
    return {"items": _service().list()}


@router.get("/{task_id}/detail", response_model=SubscriptionDetailResponse)
def get_subscription_detail(task_id: str) -> dict:
    subscription = _service().get(task_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="subscription not found")

    repository = Repository()
    runs = [
        _subscription_run_summary(item, repository.get_run(item["run_id"]))
        for item in reversed(repository.list_schedule_runs(task_id))
    ]
    return {"subscription": subscription, "runs": runs[:100]}


@router.get("/{task_id}", response_model=SubscriptionResponse)
def get_subscription(task_id: str) -> dict:
    task = _service().get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="subscription not found")
    return task


def _subscription_run_summary(schedule_run: dict, result: dict | None) -> dict:
    changes = list((result or {}).get("changes") or [])
    changed_project_ids = {
        str(item.get("project_id"))
        for item in changes
        if item.get("project_id")
    }
    projects = [
        _subscription_project(project)
        for project in (result or {}).get("projects", [])
        if str(project.get("project_id")) in changed_project_ids
    ]
    schedule_status = schedule_run["status"]
    if schedule_status in {"failed", "lease_expired"}:
        outcome = "failed"
    elif schedule_status == "running":
        outcome = "running"
    elif changed_project_ids:
        outcome = "new_content"
    else:
        outcome = "no_change"
    report = (result or {}).get("report") or {}
    return {
        **schedule_run,
        "outcome": outcome,
        "project_count": len(projects),
        "projects": projects,
        "report_available": report.get("status") == "generated",
    }


def _subscription_project(project: dict) -> dict:
    notices = [
        document.get("notice")
        for document in project.get("documents", [])
        if isinstance(document.get("notice"), dict)
    ]
    primary = max(
        notices,
        key=lambda notice: (
            notice.get("source", {}).get("authority") or 0,
            notice.get("published_at") or "",
        ),
        default={},
    )
    source = primary.get("source") or {}
    return {
        "project_id": str(project.get("project_id") or ""),
        "title": primary.get("title") or project.get("title") or "未命名项目",
        "source_name": source.get("source_name") or "来源未标注",
        "published_at": primary.get("published_at"),
        "url": source.get("source_url") or "",
        "summary": str(primary.get("core_content") or "")[:280],
    }


@router.post("/{task_id}/pause", response_model=SubscriptionResponse)
def pause_subscription(task_id: str) -> dict:
    try:
        task = _service().pause(task_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if task is None:
        raise HTTPException(status_code=404, detail="subscription not found")
    return task


@router.post("/{task_id}/resume", response_model=SubscriptionResponse)
def resume_subscription(task_id: str) -> dict:
    try:
        task = _service().resume(task_id)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if task is None:
        raise HTTPException(status_code=404, detail="subscription not found")
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_subscription(task_id: str) -> Response:
    if not _service().cancel(task_id):
        raise HTTPException(status_code=404, detail="subscription not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
