from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import unittest
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from app.schemas.tender import TaskSpec, TenderNotice
from app.sources.ccgp import CCGPAccessBlockedError, CCGPParseError, CCGPSource


FIXTURES = Path(__file__).parent / "fixtures" / "ccgp"


@dataclass
class StubResponse:
    url: str
    text: str
    status_code: int = 200


class StubTransport:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str],
        timeout: float,
    ) -> StubResponse:
        self.calls.append(
            {"url": url, "params": params, "headers": headers, "timeout": timeout}
        )
        response_url = f"{url}?{urlencode(params)}" if params else url
        return StubResponse(url=response_url, text=self.responses[url])


class FlakyTransport:
    def __init__(self, outcomes: list[Exception | str]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str],
        timeout: float,
    ) -> StubResponse:
        self.calls.append(
            {"url": url, "params": params, "headers": headers, "timeout": timeout}
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        response_url = f"{url}?{urlencode(params)}" if params else url
        return StubResponse(url=response_url, text=outcome)


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.value

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class CCGPSourceTest(unittest.IsolatedAsyncioTestCase):
    async def test_collect_searches_by_task_and_returns_contract_notices(
        self,
    ) -> None:
        detail_url = (
            "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202607/"
            "t20260710_10001.htm"
        )
        transport = StubTransport(
            {
                CCGPSource.SEARCH_URL: fixture("search_results.html"),
                detail_url: fixture("detail_tender.html"),
            }
        )
        source = CCGPSource(
            transport=transport,
            min_interval=0,
            now=lambda: datetime(
                2026, 7, 14, 12, 30, tzinfo=ZoneInfo("Asia/Shanghai")
            ),
        )
        task = TaskSpec(
            task_id="task-ccgp-001",
            query="查找上海最近两周的 GPU 服务器采购公告",
            topic="GPU 服务器",
            regions=["上海"],
            keywords=["服务器", "GPU"],
            time_range_start="2026-07-01T00:00:00+08:00",
            time_range_end="2026-07-14T23:59:59+08:00",
        )

        notices = await source.collect(task, {"max_pages": 1})

        self.assertEqual(len(notices), 1)
        self.assertIsInstance(notices[0], TenderNotice)
        notice = notices[0]
        search_call = transport.calls[0]
        self.assertIn("GPU 服务器", search_call["params"]["kw"])
        self.assertEqual(search_call["params"]["displayZone"], "上海")
        self.assertEqual(search_call["params"]["start_time"], "2026:07:01")
        self.assertEqual(search_call["params"]["end_time"], "2026:07:14")
        self.assertEqual(
            len(transport.calls), 2, "out-of-range items should not be fetched"
        )

        self.assertEqual(
            notice.title, "某研究中心 GPU 服务器采购项目公开招标公告"
        )
        self.assertEqual(
            notice.published_at.isoformat(), "2026-07-10T09:30:00+08:00"
        )
        self.assertEqual(str(notice.source.source_url), detail_url)
        self.assertIn("采购 GPU 服务器及配套高速网络设备", notice.core_content)
        self.assertEqual(notice.project_code, "SH-REDACTED-2026-001")
        self.assertEqual(notice.region, "上海市")
        self.assertEqual(notice.purchaser, "某研究中心")
        self.assertEqual(str(notice.budget), "1250000.000000")
        self.assertEqual(notice.deadline.isoformat(), "2026-07-25T10:00:00+08:00")
        self.assertEqual(len(notice.attachments), 1)
        self.assertEqual(
            str(notice.attachments[0].url),
            "https://www.ccgp.gov.cn/attachments/2026/redacted-requirements.pdf",
        )
        self.assertEqual(
            {item.field_path for item in notice.evidence},
            {
                "project_code",
                "region",
                "topic_keywords",
                "purchaser",
                "budget",
                "deadline",
            },
        )
        self.assertEqual(len(notice.raw_content_fingerprint), 64)
        self.assertEqual(len(notice.notice_stable_fingerprint), 64)
        self.assertEqual(len(notice.project_stable_fingerprint), 64)

    async def test_collect_leaves_unconfirmed_fields_empty(self) -> None:
        detail_url = (
            "https://www.ccgp.gov.cn/cggg/zygg/qtgg/202607/"
            "t20260711_20001.htm"
        )
        transport = StubTransport(
            {
                CCGPSource.SEARCH_URL: fixture("search_results_unknown.html"),
                detail_url: fixture("detail_unknown_fields.html"),
            }
        )
        source = CCGPSource(
            transport=transport,
            min_interval=0,
            now=lambda: datetime(
                2026, 7, 14, 12, 35, tzinfo=ZoneInfo("Asia/Shanghai")
            ),
        )
        task = TaskSpec(
            task_id="task-ccgp-002",
            query="查找数据治理服务采购公告",
            topic="数据治理服务",
            regions=[],
            keywords=["数据治理"],
        )

        notices = await source.collect(task, {"max_pages": 1})

        self.assertEqual(len(notices), 1)
        notice = notices[0]
        self.assertEqual(notice.project_code, "DG-REDACTED-2026-001")
        self.assertIsNone(notice.region)
        self.assertIsNone(notice.purchaser)
        self.assertIsNone(notice.budget)
        self.assertIsNone(notice.deadline)
        self.assertEqual(notice.attachments, [])
        self.assertEqual(
            {item.field_path for item in notice.evidence},
            {"project_code", "topic_keywords"},
        )

    async def test_collect_stops_on_a_security_or_rate_limit_page(
        self,
    ) -> None:
        transport = StubTransport(
            {CCGPSource.SEARCH_URL: fixture("access_blocked.html")}
        )
        source = CCGPSource(transport=transport, min_interval=0, max_retries=2)
        task = TaskSpec(
            task_id="task-ccgp-003",
            query="查找服务器采购公告",
            topic="服务器采购",
            regions=[],
            keywords=["服务器"],
        )

        with self.assertRaises(CCGPAccessBlockedError):
            await source.collect(task, {"max_pages": 1})

        self.assertEqual(
            len(transport.calls),
            1,
            "security pages must not be bypassed or retried",
        )

    async def test_collect_retries_timeouts_with_backoff_and_identifies_itself(
        self,
    ) -> None:
        transport = FlakyTransport(
            [
                TimeoutError("first timeout"),
                TimeoutError("second timeout"),
                fixture("search_results_empty.html"),
            ]
        )
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        source = CCGPSource(
            transport=transport,
            timeout=12,
            max_retries=2,
            min_interval=0,
            retry_backoff=0.25,
            sleep=fake_sleep,
        )
        task = TaskSpec(
            task_id="task-ccgp-004",
            query="查找服务器采购公告",
            topic="服务器采购",
            regions=[],
            keywords=["服务器"],
        )

        notices = await source.collect(task, {"max_pages": 1})

        self.assertEqual(notices, [])
        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(sleeps, [0.25, 0.5])
        self.assertTrue(
            all(
                call["headers"]["User-Agent"] == CCGPSource.USER_AGENT
                for call in transport.calls
            )
        )
        self.assertTrue(all(call["timeout"] == 12 for call in transport.calls))

    async def test_collect_spaces_requests_by_the_configured_minimum_interval(
        self,
    ) -> None:
        detail_url = (
            "https://www.ccgp.gov.cn/cggg/zygg/qtgg/202607/"
            "t20260711_20001.htm"
        )
        transport = StubTransport(
            {
                CCGPSource.SEARCH_URL: fixture("search_results_unknown.html"),
                detail_url: fixture("detail_unknown_fields.html"),
            }
        )
        clock = FakeClock()
        source = CCGPSource(
            transport=transport,
            max_retries=0,
            min_interval=0.75,
            sleep=clock.sleep,
            clock=clock,
        )
        task = TaskSpec(
            task_id="task-ccgp-005",
            query="查找数据治理服务采购公告",
            topic="数据治理服务",
            regions=[],
            keywords=["数据治理"],
        )

        await source.collect(task, {"max_pages": 1})

        self.assertEqual(clock.sleeps, [0.75])

    async def test_collect_does_not_invent_required_fields_from_a_list_item(
        self,
    ) -> None:
        detail_url = (
            "https://www.ccgp.gov.cn/cggg/zygg/qtgg/202607/"
            "t20260711_20001.htm"
        )
        transport = StubTransport(
            {
                CCGPSource.SEARCH_URL: fixture("search_results_unknown.html"),
                detail_url: fixture("detail_missing_required.html"),
            }
        )
        source = CCGPSource(transport=transport, min_interval=0)
        task = TaskSpec(
            task_id="task-ccgp-006",
            query="查找数据治理服务采购公告",
            topic="数据治理服务",
            regions=[],
            keywords=["数据治理"],
        )

        notices = await source.collect(task, {"max_pages": 1})

        self.assertEqual(notices, [])

    async def test_collect_searches_each_requested_region(self) -> None:
        transport = StubTransport(
            {CCGPSource.SEARCH_URL: fixture("search_results_empty.html")}
        )
        source = CCGPSource(transport=transport, min_interval=0)
        task = TaskSpec(
            task_id="task-ccgp-007",
            query="查找上海和北京的服务器采购公告",
            topic="服务器采购",
            regions=["上海", "北京"],
            keywords=["服务器"],
        )

        notices = await source.collect(task, {"max_pages": 1})

        self.assertEqual(notices, [])
        self.assertEqual(
            [call["params"]["displayZone"] for call in transport.calls],
            ["上海", "北京"],
        )

    async def test_collect_reports_an_unknown_search_page_structure(self) -> None:
        transport = StubTransport(
            {CCGPSource.SEARCH_URL: fixture("search_structure_changed.html")}
        )
        source = CCGPSource(transport=transport, min_interval=0)
        task = TaskSpec(
            task_id="task-ccgp-008",
            query="查找服务器采购公告",
            topic="服务器采购",
            regions=[],
            keywords=["服务器"],
        )

        with self.assertRaises(CCGPParseError):
            await source.collect(task, {"max_pages": 1})


if __name__ == "__main__":
    unittest.main()
