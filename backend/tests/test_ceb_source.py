from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
import unittest
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from app.schemas.tender import TaskSpec, TenderNotice
from app.sources.ceb import CEBSource


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
        params: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> StubResponse:
        self.calls.append({"url": url, "params": params})
        return StubResponse(
            url=f"{url}?{urlencode(params)}",
            text=self.responses[url],
        )


def list_page(title: str, notice_uuid: str, open_time: str) -> str:
    return f"""
    <html><body><input type="hidden" name="status" value="01" />
    <table class="table_text">
      <tr><th>公告名称</th><th>行业</th><th>地区</th><th>来源</th><th>发布时间</th></tr>
      <tr>
        <td><a href="javascript:urlOpen('{notice_uuid}')" title="{title}">{title}</a></td>
        <td><span title="信息技术">信息技术</span></td>
        <td><span title="上海市">【上海】</span></td>
        <td>发布工具</td><td>2026-07-15</td>
        <td name="openTime" id="{open_time}">加载中...</td>
      </tr>
    </table></body></html>
    """


def correction_page(
    title: str | None = None,
    notice_uuid: str = "unused",
    original_uuid: str | None = None,
) -> str:
    original_uuid = original_uuid or notice_uuid
    row = (
        f"""
        <tr><td><a href="javascript:urlOpen('{notice_uuid}')" title="{title}">
        {title}</a></td><td><a href="javascript:urlOpen('{original_uuid}')"
        title="GPU服务器项目招标公告">原公告</a></td></tr>
        """
        if title
        else ""
    )
    return f"<html><body><table class='table_text'><tr><th>更正</th></tr>{row}</table></body></html>"


class CEBSourceTest(unittest.IsolatedAsyncioTestCase):
    async def test_collect_uses_native_categories_and_official_active_filter(self) -> None:
        responses = {
            CEBSource.CORRECTION_AUDIT_URL: correction_page(),
            CEBSource.CATEGORY_URLS["prequalification"]: list_page(
                "GPU服务器项目资格预审公告",
                "pre001",
                "2026-07-20 17:00:00",
            ),
            CEBSource.CATEGORY_URLS["tender"]: list_page(
                "GPU服务器项目招标公告",
                "tender001",
                "2026-07-25 10:00:00",
            ),
        }
        transport = StubTransport(responses)
        source = CEBSource(
            transport=transport,
            now=lambda: datetime(
                2026, 7, 15, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")
            ),
        )
        task = TaskSpec(
            task_id="ceb-001",
            query="GPU服务器招标",
            topic="GPU服务器",
            keywords=["GPU", "服务器"],
        )

        notices = await source.collect(task, {"max_pages": 1})

        self.assertTrue(all(isinstance(notice, TenderNotice) for notice in notices))
        self.assertEqual(
            [notice.notice_type for notice in notices],
            ["tender", "tender"],
        )
        self.assertEqual(
            [notice.opportunity_kind for notice in notices],
            ["prequalification", "tender"],
        )
        self.assertEqual(len(transport.calls), 3)
        self.assertNotIn("correction", CEBSource.CATEGORY_URLS)
        category_calls = [
            call
            for call in transport.calls
            if call["url"] in CEBSource.CATEGORY_URLS.values()
        ]
        self.assertTrue(all(call["params"]["status"] == "01" for call in category_calls))
        self.assertTrue(all(call["params"]["word"] == "GPU服务器" for call in category_calls))
        self.assertTrue(all(call["params"]["dates"] == "" for call in category_calls))
        self.assertTrue(
            all(call["params"]["signDate"].endswith(",lt") for call in category_calls)
        )
        for notice in notices:
            self.assertGreater(
                notice.deadline,
                datetime(2026, 7, 15, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )
            self.assertIn(
                "notice_type", {item.field_path for item in notice.evidence}
            )
            self.assertIn(
                "participation_status",
                {item.field_path for item in notice.evidence},
            )
            self.assertEqual(str(notice.source.source_url).split("#", 1)[0], "https://ctbpsp.com/")

    async def test_collect_rejects_polluted_categories_and_expired_open_time(self) -> None:
        transport = StubTransport(
            {
                CEBSource.CORRECTION_AUDIT_URL: correction_page(
                    "GPU服务器项目终止公告",
                    "change-001",
                    "expired-tender",
                ),
                CEBSource.CATEGORY_URLS["prequalification"]: list_page(
                    "GPU服务器询比采购公告",
                    "polluted-pre",
                    "2026-07-25 10:00:00",
                ),
                CEBSource.CATEGORY_URLS["tender"]: list_page(
                    "GPU服务器项目招标公告",
                    "expired-tender",
                    "2026-07-25 10:00:00",
                ),
            }
        )
        source = CEBSource(
            transport=transport,
            now=lambda: datetime(
                2026, 7, 15, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")
            ),
        )
        task = TaskSpec(
            task_id="ceb-negative",
            query="GPU服务器",
            topic="GPU服务器",
            keywords=["GPU", "服务器"],
        )

        self.assertEqual(await source.collect(task, {"max_pages": 1}), [])


if __name__ == "__main__":
    unittest.main()
