from datetime import time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator


Frequency = Literal["once", "daily", "weekly"]
WeeklyDay = Literal[
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


class TaskRunRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    frequency: Frequency = "once"
    subject: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=50)


class TaskRunResponse(BaseModel):
    task_id: str
    run_id: str
    status: str
    task_spec: dict
    selected_sources: list[dict]
    steps: list[dict]
    funnel: dict[str, int]
    projects: list[dict]
    changes: list[dict]
    quality_passed: bool
    quality_issues: list[str]
    ai: dict
    report: dict


class SubscriptionCreateRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    frequency: Frequency
    timezone: str = "Asia/Shanghai"
    local_time: str | None = None
    weekly_day: WeeklyDay | None = None
    run_at: AwareDatetime | None = None
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_backoff_seconds: int = Field(default=30, ge=1, le=3600)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("timezone must be a valid IANA timezone") from error
        return value

    @field_validator("local_time")
    @classmethod
    def validate_local_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = time.fromisoformat(value)
        except ValueError as error:
            raise ValueError("local_time must use HH:MM") from error
        if parsed.second or parsed.microsecond:
            raise ValueError("local_time must use minute precision")
        return parsed.strftime("%H:%M")

    @model_validator(mode="after")
    def validate_schedule_shape(self) -> "SubscriptionCreateRequest":
        if self.frequency == "once":
            if self.run_at is None:
                raise ValueError("once schedule requires run_at")
            if self.weekly_day is not None:
                raise ValueError("weekly_day is only valid for weekly schedules")
            if self.local_time is None:
                self.local_time = self.run_at.astimezone(ZoneInfo(self.timezone)).strftime("%H:%M")
        else:
            if self.run_at is not None:
                raise ValueError("run_at is only valid for once schedules")
            if self.local_time is None:
                self.local_time = "09:00"
            if self.frequency == "weekly" and self.weekly_day is None:
                raise ValueError("weekly schedule requires weekly_day")
            if self.frequency == "daily" and self.weekly_day is not None:
                raise ValueError("weekly_day is only valid for weekly schedules")
        return self


class SubscriptionResponse(BaseModel):
    task_id: str
    query: str
    frequency: Frequency
    timezone: str
    local_time: str
    weekly_day: WeeklyDay | None
    run_at: AwareDatetime | None
    next_run_at: AwareDatetime
    status: Literal["active", "paused", "completed", "failed"]
    retry_count: int
    max_retries: int
    retry_backoff_seconds: int
    last_run_at: AwareDatetime | None
    last_error: str | None
    lease_owner: str | None
    lease_expires_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class SubscriptionListResponse(BaseModel):
    items: list[SubscriptionResponse]


class NaturalLanguageSubscriptionCreateRequest(BaseModel):
    query: str = Field(max_length=500)
    timezone: str = "Asia/Shanghai"
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_backoff_seconds: int = Field(default=30, ge=1, le=3600)


class ScheduleIntentResponse(BaseModel):
    frequency: Frequency
    timezone: str
    local_time: str
    weekly_day: WeeklyDay | None
    run_at: AwareDatetime | None
    search_query: str
    matched_text: str


class NaturalLanguageSubscriptionCreateResponse(BaseModel):
    subscription: SubscriptionResponse
    parsed: ScheduleIntentResponse
