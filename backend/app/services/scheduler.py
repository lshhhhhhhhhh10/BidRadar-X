from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Protocol, cast
from uuid import uuid4
from zoneinfo import ZoneInfo


WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class LocalScheduler:
    """Calculate future instants from explicit local scheduling parameters."""

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock or SystemClock()

    def next_run_at(
        self,
        frequency: str,
        *,
        timezone_name: str | None = None,
        local_time: str = "09:00",
        weekly_day: str | None = None,
        run_at: datetime | None = None,
        after: datetime | None = None,
    ) -> datetime | str | None:
        reference = self._aware_utc(after or self.clock.now())
        legacy_call = timezone_name is None
        if legacy_call:
            if frequency == "once":
                return None
            if frequency in {"daily", "weekly"}:
                days = 1 if frequency == "daily" else 7
                return (reference + timedelta(days=days)).isoformat(timespec="seconds")
            raise ValueError(f"unsupported frequency: {frequency}")

        if frequency == "once":
            if run_at is None:
                raise ValueError("once schedule requires run_at")
            result = self._aware_utc(run_at)
            if result <= reference:
                raise ValueError("run_at must be in the future")
            return result

        zone = ZoneInfo(timezone_name)
        wall_time = time.fromisoformat(local_time)
        local_reference = reference.astimezone(zone)
        if frequency == "daily":
            candidate = self._valid_local_candidate(
                local_reference.date(), wall_time, zone
            )
            if candidate <= local_reference:
                candidate = self._valid_local_candidate(
                    local_reference.date() + timedelta(days=1), wall_time, zone
                )
            return candidate.astimezone(timezone.utc)

        if frequency == "weekly":
            if weekly_day not in WEEKDAYS:
                raise ValueError("weekly schedule requires a valid weekly_day")
            days_ahead = (WEEKDAYS[weekly_day] - local_reference.weekday()) % 7
            candidate = self._valid_local_candidate(
                local_reference.date() + timedelta(days=days_ahead),
                wall_time,
                zone,
            )
            if candidate <= local_reference:
                candidate = self._valid_local_candidate(
                    local_reference.date() + timedelta(days=days_ahead + 7),
                    wall_time,
                    zone,
                )
            return candidate.astimezone(timezone.utc)

        raise ValueError(f"unsupported frequency: {frequency}")

    @staticmethod
    def _aware_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduled datetimes must include a timezone")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _valid_local_candidate(
        local_date: date,
        wall_time: time,
        zone: ZoneInfo,
    ) -> datetime:
        naive = datetime.combine(local_date, wall_time)
        for minute_offset in range(181):
            adjusted = naive + timedelta(minutes=minute_offset)
            candidate = adjusted.replace(tzinfo=zone, fold=0)
            round_trip = candidate.astimezone(timezone.utc).astimezone(zone)
            if round_trip.replace(tzinfo=None) == adjusted:
                return candidate
        raise ValueError("local_time does not resolve within the timezone transition window")


class SubscriptionService:
    def __init__(
        self,
        *,
        repository: Any,
        scheduler: LocalScheduler,
        clock: Clock,
    ) -> None:
        self.repository = repository
        self.scheduler = scheduler
        self.clock = clock

    def create(
        self,
        *,
        query: str,
        frequency: str,
        timezone_name: str,
        local_time: str,
        weekly_day: str | None,
        run_at: datetime | None,
        max_retries: int,
        retry_backoff_seconds: int,
    ) -> dict[str, Any]:
        now = self.clock.now()
        next_run_at = cast(datetime, self.scheduler.next_run_at(
            frequency=frequency,
            timezone_name=timezone_name,
            local_time=local_time,
            weekly_day=weekly_day,
            run_at=run_at,
            after=now,
        ))
        return self.repository.create_subscription(
            task_id=str(uuid4()),
            query=query,
            frequency=frequency,
            timezone_name=timezone_name,
            local_time=local_time,
            weekly_day=weekly_day,
            run_at=run_at,
            next_run_at=next_run_at,
            now=now,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )

    def get(self, task_id: str) -> dict[str, Any] | None:
        return self.repository.get_subscription(task_id)

    def list(self) -> list[dict[str, Any]]:
        return self.repository.list_subscriptions()

    def pause(self, task_id: str) -> dict[str, Any] | None:
        return self.repository.pause_subscription(task_id, now=self.clock.now())

    def resume(self, task_id: str) -> dict[str, Any] | None:
        task = self.repository.get_subscription(task_id)
        if task is None:
            return None
        now = self.clock.now()
        run_at = datetime.fromisoformat(task["run_at"]) if task["run_at"] else None
        if task["frequency"] == "once" and run_at is not None and run_at <= now:
            next_run_at = now
        else:
            next_run_at = cast(datetime, self.scheduler.next_run_at(
                frequency=task["frequency"],
                timezone_name=task["timezone"],
                local_time=task["local_time"],
                weekly_day=task["weekly_day"],
                run_at=run_at,
                after=now,
            ))
        return self.repository.resume_subscription(
            task_id,
            next_run_at=next_run_at,
            now=now,
        )

    def cancel(self, task_id: str) -> bool:
        return self.repository.delete_subscription(task_id)
