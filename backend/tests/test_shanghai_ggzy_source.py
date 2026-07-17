from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
import unittest
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from app.schemas.tender import TaskSpec, TenderNotice
from app.sources.shanghai_ggzy import ShanghaiGGZYSource


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
        self.calls.append({"url": url, "params": params})
        response_url = f"{url}?{urlencode(params)}" if params else url
        key = (
            f"{url}#{params['channelId']}"
            if url == ShanghaiGGZYSource.LIST_URL and params
            else url
        )
        return StubResponse(url=response_url, text=self.responses[key])


def list_page(channel_id: str = "2662", *, include_rows: bool = True) -> str:
    rows = [
        ("pre-001", "GPU服务器项目资格预审公告", "SH-PRE-001"),
        ("tender-001", "GPU服务器项目招标公告", "SH-TENDER-001"),
        ("past-001", "GPU服务器机房项目招标公告", "SH-PAST-001"),
        ("result-001", "GPU服务器项目中标结果公告", "SH-RESULT-001"),
    ]
    items = "".join(
        f"""
        <li onclick="window.open('/gqcgzbgg/{marker}?cExt=&isIndex=')">
          <span class="cs-leftSpan"></span>
          <span class="cs-span2">{title}</span>
          <span>{project_code}</span><span>2026-07-15</span>
        </li>
        """
        for marker, title, project_code in rows
    ) if include_rows else ""
    return f"""
    <html><body>
      <input type="hidden" id="channelId" name="channelId" value="{channel_id}" />
      <div id="allList"><ul>{items}</ul></div>
    </body></html>
    """


def detail_page(body: str) -> str:
    return f"<html><body><div class='content'>{body}</div></body></html>"


class ShanghaiGGZYSourceTest(unittest.IsolatedAsyncioTestCase):
    async def test_collect_classifies_body_sections_and_requires_future_deadline(self) -> None:
        responses = {
            f"{ShanghaiGGZYSource.LIST_URL}#2662": list_page(),
            f"{ShanghaiGGZYSource.LIST_URL}#2663": list_page("2663", include_rows=False),
            f"{ShanghaiGGZYSource.LIST_URL}#2666": list_page("2666", include_rows=False),
            "https://www.shggzy.com/gqcgzbgg/pre-001?cExt=&isIndex=": detail_page(
                "<p>四、资格预审文件的获取</p>"
                "<p>五、资格预审申请文件的递交</p>"
                "<p>递交截止时间：2026年07月20日17:00</p>"
            ),
            "https://www.shggzy.com/gqcgzbgg/tender-001?cExt=&isIndex=": detail_page(
                "<p>四、招标文件的获取</p>"
                "<p><a href='/files/tender-001.pdf'>招标文件下载</a></p>"
                "<p>六、投标文件递交</p>"
                "<p>递交截止时间：2026年07月25日10:00</p>"
            ),
            "https://www.shggzy.com/gqcgzbgg/past-001?cExt=&isIndex=": detail_page(
                "<p>四、招标文件的获取</p>"
                "<p>六、投标文件递交</p>"
                "<p>递交截止时间：2026年07月14日10:00</p>"
            ),
        }
        transport = StubTransport(responses)
        source = ShanghaiGGZYSource(
            transport=transport,
            now=lambda: datetime(
                2026, 7, 15, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")
            ),
        )
        task = TaskSpec(
            task_id="sh-001",
            query="上海GPU服务器招标",
            topic="GPU服务器",
            regions=["上海"],
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
        self.assertEqual(len(transport.calls), 6)
        self.assertNotIn("2663", ShanghaiGGZYSource.ENABLED_CHANNELS)
        list_calls = [call for call in transport.calls if call["params"] is not None]
        self.assertTrue(all(call["params"]["title"] == "GPU服务器" for call in list_calls))
        self.assertTrue(all(call["params"]["inDates"] == "" for call in list_calls))
        for notice in notices:
            self.assertGreater(
                notice.deadline,
                datetime(2026, 7, 15, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )
            self.assertTrue(
                {"notice_type", "deadline", "participation_status"}.issubset(
                    {item.field_path for item in notice.evidence}
                )
            )
        tender_notice = next(
            notice for notice in notices if notice.opportunity_kind == "tender"
        )
        self.assertEqual(len(tender_notice.attachments), 1)
        self.assertEqual(tender_notice.attachments[0].name, "招标文件下载")
        self.assertEqual(
            str(tender_notice.attachments[0].url),
            "https://www.shggzy.com/files/tender-001.pdf",
        )

    async def test_empty_200_response_is_a_source_failure_not_zero_results(self) -> None:
        source = ShanghaiGGZYSource(
            transport=StubTransport(
                {f"{ShanghaiGGZYSource.LIST_URL}#2663": ""}
            )
        )
        task = TaskSpec(
            task_id="sh-empty",
            query="GPU服务器",
            topic="GPU服务器",
            keywords=["GPU"],
        )

        with self.assertRaisesRegex(Exception, "empty"):
            await source.collect(task, {"max_pages": 1})


if __name__ == "__main__":
    unittest.main()
