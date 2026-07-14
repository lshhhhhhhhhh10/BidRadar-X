from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import ValidationError

from ..schemas.task import (
    NaturalLanguageSubscriptionCreateRequest,
    NaturalLanguageSubscriptionCreateResponse,
    SubscriptionCreateRequest,
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


@router.get("/{task_id}", response_model=SubscriptionResponse)
def get_subscription(task_id: str) -> dict:
    task = _service().get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="subscription not found")
    return task


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
