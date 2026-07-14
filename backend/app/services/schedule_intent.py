from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..schemas.task import Frequency, WeeklyDay


WEEKDAYS = {
    "一": "monday",
    "二": "tuesday",
    "三": "wednesday",
    "四": "thursday",
    "五": "friday",
    "六": "saturday",
    "日": "sunday",
    "天": "sunday",
}

TIME_PATTERN = re.compile(
    r"(?P<clock>\d{1,2}):(?P<minute>\d{2})"
    r"|(?:(?P<period>上午|早上|早晨|凌晨|中午|下午|晚上|傍晚)\s*)?"
    r"(?P<hour>\d{1,2})\s*(?:点|时)"
    r"(?:(?P<half>半)|(?P<cn_minute>\d{1,2})\s*分?)?"
)


@dataclass(frozen=True)
class ScheduleIntent:
    frequency: Frequency
    timezone: str
    local_time: str
    weekly_day: WeeklyDay | None
    run_at: datetime | None
    search_query: str
    matched_text: str


class ScheduleIntentError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ScheduleIntentParser:
    """Parse explicit Chinese schedule phrases without external model calls."""

    def parse(
        self,
        query: str,
        *,
        now: datetime,
        timezone: str = "Asia/Shanghai",
    ) -> ScheduleIntent:
        try:
            zone = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ScheduleIntentError(
                "schedule_invalid",
                "timezone must be a valid IANA timezone",
            ) from error
        if now.tzinfo is None or now.utcoffset() is None:
            raise ScheduleIntentError(
                "schedule_invalid",
                "now must include a timezone",
            )

        normalized = re.sub(r"\s+", " ", query.strip().replace("：", ":"))
        daily_match = re.search(r"每天|每日", normalized)
        weekly_matches = list(re.finditer(r"(?:每周|周)([一二三四五六日天])", normalized))
        date_matches = list(re.finditer(r"\d{4}-\d{2}-\d{2}", normalized))
        tomorrow_match = re.search(r"明天", normalized)
        time_matches = list(TIME_PATTERN.finditer(normalized))
        schedule_found = any(
            (
                daily_match is not None,
                bool(weekly_matches),
                bool(date_matches),
                tomorrow_match is not None,
            )
        )
        if not schedule_found:
            raise ScheduleIntentError(
                "schedule_not_found",
                "query does not contain a supported schedule expression",
            )
        if not time_matches:
            raise ScheduleIntentError(
                "schedule_invalid",
                "schedule expression must include an explicit time",
            )

        cadence_count = sum(
            (
                daily_match is not None,
                bool(weekly_matches),
                bool(date_matches) or tomorrow_match is not None,
            )
        )
        if cadence_count > 1 or (date_matches and tomorrow_match is not None):
            raise ScheduleIntentError(
                "schedule_ambiguous",
                "query contains conflicting schedule frequencies or dates",
            )

        weekly_days = {match.group(1) for match in weekly_matches}
        if len(weekly_days) > 1:
            raise ScheduleIntentError(
                "schedule_ambiguous",
                "query contains more than one weekday",
            )

        date_values = {match.group(0) for match in date_matches}
        if len(date_values) > 1:
            raise ScheduleIntentError(
                "schedule_ambiguous",
                "query contains more than one date",
            )

        parsed_times = [self._parse_time(match) for match in time_matches]
        unique_times = set(parsed_times)
        if len(unique_times) > 1:
            raise ScheduleIntentError(
                "schedule_ambiguous",
                "query contains more than one distinct time",
            )
        hour, minute = parsed_times[0]

        search_query = normalized
        schedule_matches = [
            match
            for match in [daily_match, tomorrow_match, *weekly_matches, *date_matches]
            if match is not None
        ]
        removable_matches = schedule_matches + time_matches
        for match in sorted(removable_matches, key=lambda item: item.start(), reverse=True):
            search_query = search_query[: match.start()] + search_query[match.end() :]
        search_query = re.sub(r"\s+", " ", search_query).strip(" ,，。；;：:")
        if not search_query:
            raise ScheduleIntentError(
                "empty_search_query",
                "schedule expression does not contain a business search query",
            )

        run_at = None
        if date_matches or tomorrow_match is not None:
            if date_matches:
                try:
                    local_date = datetime.strptime(date_matches[0].group(0), "%Y-%m-%d").date()
                except ValueError as error:
                    raise ScheduleIntentError(
                        "schedule_invalid",
                        "date must be a valid YYYY-MM-DD value",
                    ) from error
            else:
                local_date = now.astimezone(zone).date() + timedelta(days=1)
            run_at = datetime(
                local_date.year,
                local_date.month,
                local_date.day,
                hour,
                minute,
                tzinfo=zone,
            )
            if run_at <= now.astimezone(zone):
                raise ScheduleIntentError(
                    "schedule_in_past",
                    "one-time schedule must be in the future",
                )

        weekly_match = weekly_matches[0] if weekly_matches else None
        matched_text = " ".join(
            match.group(0)
            for match in sorted(removable_matches, key=lambda item: item.start())
        )

        return ScheduleIntent(
            frequency=(
                "daily"
                if daily_match is not None
                else "weekly"
                if weekly_match is not None
                else "once"
            ),
            timezone=timezone,
            local_time=f"{hour:02d}:{minute:02d}",
            weekly_day=WEEKDAYS[weekly_match.group(1)] if weekly_match is not None else None,
            run_at=run_at,
            search_query=search_query,
            matched_text=matched_text,
        )

    @staticmethod
    def _parse_time(match: re.Match[str]) -> tuple[int, int]:
        if match.group("clock") is not None:
            hour = int(match.group("clock"))
            minute = int(match.group("minute"))
            if hour > 23 or minute > 59:
                raise ScheduleIntentError(
                    "schedule_invalid",
                    "time must be a valid twenty-four-hour clock value",
                )
            return hour, minute

        period = match.group("period")
        hour = int(match.group("hour"))
        minute = (
            30
            if match.group("half") is not None
            else int(match.group("cn_minute") or 0)
        )
        if minute > 59:
            raise ScheduleIntentError("schedule_invalid", "minute must be between 0 and 59")
        if period is not None:
            if not 1 <= hour <= 12:
                raise ScheduleIntentError(
                    "schedule_invalid",
                    "time period requires an hour between 1 and 12",
                )
            if period in {"上午", "早上", "早晨", "凌晨"} and hour == 12:
                hour = 0
            elif period in {"中午", "下午", "晚上", "傍晚"} and hour != 12:
                hour += 12
        elif hour > 23:
            raise ScheduleIntentError(
                "schedule_invalid",
                "hour must be between 0 and 23",
            )
        return hour, minute
