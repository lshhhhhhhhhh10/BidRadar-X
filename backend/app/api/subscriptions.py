from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from ..schemas.task import (
    SubscriptionCreateRequest,
    SubscriptionListResponse,
    SubscriptionResponse,
)
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


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
def create_subscription(request: SubscriptionCreateRequest) -> dict:
    try:
        return _service().create(
            query=request.query,
            frequency=request.frequency,
            timezone_name=request.timezone,
            local_time=request.local_time or "09:00",
            weekly_day=request.weekly_day,
            run_at=request.run_at,
            max_retries=request.max_retries,
            retry_backoff_seconds=request.retry_backoff_seconds,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


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
