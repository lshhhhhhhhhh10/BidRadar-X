from __future__ import annotations

from datetime import datetime, timezone
import unittest

from app.services.schedule_intent import ScheduleIntentError, ScheduleIntentParser


class ScheduleIntentParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc)
        self.parser = ScheduleIntentParser()

    def test_daily_morning_time_is_separated_from_the_search_query(self) -> None:
        result = self.parser.parse(
            "每天上午9点查询安徽省服务器采购项目",
            now=self.now,
        )

        self.assertEqual(result.frequency, "daily")
        self.assertEqual(result.timezone, "Asia/Shanghai")
        self.assertEqual(result.local_time, "09:00")
        self.assertIsNone(result.weekly_day)
        self.assertIsNone(result.run_at)
        self.assertEqual(result.search_query, "查询安徽省服务器采购项目")

    def test_three_minute_interval_is_parsed_without_requiring_a_clock(self) -> None:
        result = self.parser.parse(
            "每隔三分钟查询全国范围内的人工智能采购信息",
            now=self.now,
        )

        self.assertEqual(result.frequency, "interval")
        self.assertEqual(result.interval_minutes, 3)
        self.assertEqual(result.search_query, "查询全国范围内的人工智能采购信息")
        self.assertIsNone(result.run_at)

    def test_interval_shorter_than_three_minutes_is_rejected(self) -> None:
        with self.assertRaises(ScheduleIntentError) as caught:
            self.parser.parse("每隔2分钟查询服务器采购", now=self.now)

        self.assertEqual(caught.exception.code, "interval_too_short")

    def test_weekly_afternoon_time_uses_the_requested_weekday(self) -> None:
        result = self.parser.parse(
            "每周一下午3点查询上海市计算设备采购",
            now=self.now,
        )

        self.assertEqual(result.frequency, "weekly")
        self.assertIsNone(result.interval_minutes)
        self.assertEqual(result.local_time, "15:00")
        self.assertEqual(result.weekly_day, "monday")
        self.assertEqual(result.search_query, "查询上海市计算设备采购")

    def test_absolute_date_creates_a_timezone_aware_once_schedule(self) -> None:
        result = self.parser.parse(
            "2026-07-20 上午9点查询安徽服务器采购",
            now=self.now,
        )

        self.assertEqual(result.frequency, "once")
        self.assertEqual(result.local_time, "09:00")
        self.assertEqual(result.run_at.isoformat(), "2026-07-20T09:00:00+08:00")
        self.assertEqual(result.search_query, "查询安徽服务器采购")

    def test_twenty_four_hour_time_tolerates_spacing_and_chinese_punctuation(self) -> None:
        result = self.parser.parse(
            "  每日  14：30，查询人工智能平台招标。 ",
            now=self.now,
        )

        self.assertEqual(result.frequency, "daily")
        self.assertEqual(result.local_time, "14:30")
        self.assertEqual(result.search_query, "查询人工智能平台招标")

    def test_tomorrow_is_resolved_from_the_injected_clock(self) -> None:
        result = self.parser.parse(
            "明天下午3点查询服务器项目",
            now=self.now,
        )

        self.assertEqual(result.frequency, "once")
        self.assertEqual(result.run_at.isoformat(), "2026-07-15T15:00:00+08:00")
        self.assertEqual(result.search_query, "查询服务器项目")

    def test_query_without_a_schedule_has_a_stable_error_code(self) -> None:
        with self.assertRaises(ScheduleIntentError) as caught:
            self.parser.parse("查询安徽省服务器采购项目", now=self.now)

        self.assertEqual(caught.exception.code, "schedule_not_found")

    def test_missing_time_is_invalid_instead_of_defaulting_to_nine(self) -> None:
        with self.assertRaises(ScheduleIntentError) as caught:
            self.parser.parse("每天查询服务器项目", now=self.now)

        self.assertEqual(caught.exception.code, "schedule_invalid")

    def test_invalid_hour_has_a_stable_invalid_error(self) -> None:
        with self.assertRaises(ScheduleIntentError) as caught:
            self.parser.parse("每天25点查询服务器项目", now=self.now)

        self.assertEqual(caught.exception.code, "schedule_invalid")

    def test_multiple_weekdays_are_ambiguous(self) -> None:
        with self.assertRaises(ScheduleIntentError) as caught:
            self.parser.parse("每周一周二9点查询服务器项目", now=self.now)

        self.assertEqual(caught.exception.code, "schedule_ambiguous")

    def test_conflicting_daily_and_weekly_expressions_are_ambiguous(self) -> None:
        with self.assertRaises(ScheduleIntentError) as caught:
            self.parser.parse("每天每周一9点查询服务器项目", now=self.now)

        self.assertEqual(caught.exception.code, "schedule_ambiguous")

    def test_different_times_are_ambiguous(self) -> None:
        with self.assertRaises(ScheduleIntentError) as caught:
            self.parser.parse("每天上午9点下午3点查询服务器项目", now=self.now)

        self.assertEqual(caught.exception.code, "schedule_ambiguous")

    def test_past_absolute_time_is_rejected(self) -> None:
        with self.assertRaises(ScheduleIntentError) as caught:
            self.parser.parse("2026-07-14 上午9点查询服务器项目", now=self.now)

        self.assertEqual(caught.exception.code, "schedule_in_past")

    def test_schedule_without_a_business_query_is_rejected(self) -> None:
        with self.assertRaises(ScheduleIntentError) as caught:
            self.parser.parse("每天上午9点", now=self.now)

        self.assertEqual(caught.exception.code, "empty_search_query")

    def test_noon_definitions_are_explicit(self) -> None:
        morning = self.parser.parse("每天上午12点查询项目", now=self.now)
        afternoon = self.parser.parse("每天下午12点查询项目", now=self.now)

        self.assertEqual(morning.local_time, "00:00")
        self.assertEqual(afternoon.local_time, "12:00")

    def test_evening_time_and_friday_clock_are_supported(self) -> None:
        evening = self.parser.parse("每天晚上8点查询服务器项目", now=self.now)
        friday = self.parser.parse("每周五 09:00 查询全国服务器项目", now=self.now)

        self.assertEqual(evening.local_time, "20:00")
        self.assertEqual(friday.weekly_day, "friday")
        self.assertEqual(friday.local_time, "09:00")
        self.assertEqual(friday.search_query, "查询全国服务器项目")

    def test_time_without_a_cadence_or_date_is_not_a_schedule(self) -> None:
        with self.assertRaises(ScheduleIntentError) as caught:
            self.parser.parse("上午9点查询服务器项目", now=self.now)

        self.assertEqual(caught.exception.code, "schedule_not_found")

    def test_invalid_timezone_is_reported_as_an_invalid_schedule(self) -> None:
        with self.assertRaises(ScheduleIntentError) as caught:
            self.parser.parse(
                "每天上午9点查询服务器项目",
                now=self.now,
                timezone="Mars/Olympus",
            )

        self.assertEqual(caught.exception.code, "schedule_invalid")

    def test_half_hour_is_consumed_instead_of_leaking_into_the_search_query(self) -> None:
        result = self.parser.parse("每天上午9点半查询服务器项目", now=self.now)

        self.assertEqual(result.local_time, "09:30")
        self.assertEqual(result.search_query, "查询服务器项目")


if __name__ == "__main__":
    unittest.main()
