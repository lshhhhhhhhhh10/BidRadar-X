from datetime import datetime
from pathlib import Path
import unittest

from app.schemas.tender import TaskSpec, TenderNotice
from app.sources.ggzy import (
    GGZYAccessRestrictedError,
    GGZYHTTPResponse,
    GGZYSource,
    GGZYStructureChangedError,
    GGZYTimeoutError,
    parse_search_response,
)


FIXTURES = Path(__file__).parent / "fixtures" / "ggzy"


class GGZYDetailParserTest(unittest.TestCase):
    def test_parses_public_detail_fixture_into_tender_notice(self) -> None:
        fetched_at = datetime.fromisoformat("2026-07-14T12:30:00+08:00")
        source = GGZYSource(now=lambda: fetched_at)
        html = (FIXTURES / "detail_primary.html").read_text(encoding="utf-8")

        notice = source.parse_notice_html(
            html,
            source_url=(
                "https://www.ggzy.gov.cn/information/deal/html/a/340000/"
                "0201/20260712/abcdef0123456789.html"
            ),
            region="安徽省",
            region_evidence_url="https://www.ggzy.gov.cn/information/pubTradingInfo/getTradList",
            region_evidence_quote='{"province":"安徽省"}',
            region_evidence_locator=(
                '{"method":"POST","source_notice_id":"abcdef0123456789",'
                '"field":"province"}'
            ),
            topic_terms=["计算设备"],
        )

        self.assertIsInstance(notice, TenderNotice)
        self.assertEqual(notice.title, "某市数据中心计算设备采购项目采购公告")
        self.assertEqual(notice.published_at.isoformat(), "2026-07-12T09:30:00+08:00")
        self.assertEqual(notice.purchaser, "某市大数据管理中心")
        self.assertEqual(notice.project_code, "ZXCG-2026-0712")
        self.assertEqual(notice.region, "安徽省")
        self.assertEqual(notice.topic_keywords, ["计算设备"])
        self.assertIn("采购计算设备、存储设备及配套软件服务", notice.core_content)
        self.assertNotIn("网站地图", notice.core_content)
        self.assertEqual(len(notice.attachments), 1)
        self.assertEqual(
            str(notice.attachments[0].url),
            "https://www.ggzy.gov.cn/files/ZXCG-2026-0712/%E9%87%87%E8%B4%AD%E9%9C%80%E6%B1%82.pdf",
        )
        self.assertEqual(notice.source.source_name, "全国公共资源交易平台")
        self.assertEqual(notice.fetched_at, fetched_at)
        self.assertEqual(
            {item.field_path for item in notice.evidence},
            {
                "project_code",
                "region",
                "topic_keywords",
                "purchaser",
                "source.original_source_name",
            },
        )

    def test_project_fingerprint_is_stable_across_notice_lifecycle(self) -> None:
        fetched_at = datetime.fromisoformat("2026-07-14T12:30:00+08:00")
        source = GGZYSource(now=lambda: fetched_at)
        tender_html = (FIXTURES / "detail_primary.html").read_text(encoding="utf-8")
        award_html = tender_html.replace("采购公告", "中标（成交）结果公告")
        url = "https://www.ggzy.gov.cn/information/deal/lifecycle.html"

        tender = source.parse_notice_html(tender_html, source_url=url)
        award = source.parse_notice_html(award_html, source_url=url)

        self.assertNotEqual(
            tender.notice_stable_fingerprint,
            award.notice_stable_fingerprint,
        )
        self.assertEqual(
            tender.project_stable_fingerprint,
            award.project_stable_fingerprint,
        )

    def test_changed_detail_structure_fails_loudly(self) -> None:
        source = GGZYSource()
        html = (FIXTURES / "detail_structure_changed.html").read_text(
            encoding="utf-8"
        )

        with self.assertRaisesRegex(
            GGZYStructureChangedError, "content container"
        ):
            source.parse_notice_html(
                html,
                source_url="https://www.ggzy.gov.cn/information/deal/changed.html",
                published_at="2026-07-14",
            )


class GGZYSearchParserTest(unittest.TestCase):
    def test_parses_current_official_public_api_shape(self) -> None:
        page = parse_search_response(
            {
                "code": 200,
                "ttlpage": 1,
                "data": [
                    {
                        "id": "notice-current-1",
                        "title": "某市服务器设备采购公告",
                        "url": "/information/deal/html/a/110000/20260717/one.html",
                        "publishTime": "2026-07-17 10:00:00",
                        "provinceText": "北京市",
                        "transactionSourcesPlatformText": "北京市公共资源交易平台",
                    }
                ],
            }
        )

        self.assertEqual(page.total_pages, 1)
        self.assertEqual(page.results[0].region, "北京市")
        self.assertEqual(page.results[0].source_name, "北京市公共资源交易平台")
        self.assertTrue(page.results[0].source_url.startswith("https://www.ggzy.gov.cn/"))

    def test_current_api_captcha_code_fails_loudly(self) -> None:
        with self.assertRaises(GGZYAccessRestrictedError):
            parse_search_response({"code": 829, "msg": "需要验证码", "data": []})

    def test_empty_result_fixture_is_a_valid_search_page(self) -> None:
        page = parse_search_response((FIXTURES / "search_empty.json").read_bytes())

        self.assertEqual(page.results, [])
        self.assertEqual(page.total_pages, 0)

    def test_changed_search_structure_fails_loudly(self) -> None:
        with self.assertRaisesRegex(GGZYStructureChangedError, "collection"):
            parse_search_response(
                (FIXTURES / "search_structure_changed.json").read_bytes()
            )

    def test_access_restriction_is_not_treated_as_an_empty_result(self) -> None:
        with self.assertRaises(GGZYAccessRestrictedError):
            parse_search_response((FIXTURES / "access_restricted.html").read_bytes())


class FixtureTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str] | None]] = []
        self.detail_by_url = {
            "https://www.ggzy.gov.cn/information/deal/html/a/340000/0201/20260712/abcdef0123456789.html": (
                FIXTURES / "detail_primary.html"
            ).read_bytes(),
            "https://www.ggzy.gov.cn/information/deal/html/a/340000/0101/20260713/fedcba9876543210.html": (
                FIXTURES / "detail_alternate.html"
            ).read_bytes(),
        }

    async def request(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None,
        headers: dict[str, str],
        timeout: float,
    ) -> GGZYHTTPResponse:
        self.calls.append((method, url, data))
        if method == "POST":
            assert data is not None
            page = data["PAGENUMBER"]
            return GGZYHTTPResponse(
                status=200,
                url=url,
                body=(FIXTURES / f"search_page_{page}.json").read_bytes(),
                headers={"content-type": "application/json; charset=utf-8"},
            )
        return GGZYHTTPResponse(
            status=200,
            url=url,
            body=self.detail_by_url[url],
            headers={"content-type": "text/html; charset=utf-8"},
        )


class GGZYCollectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_collect_applies_filters_and_follows_all_result_pages(self) -> None:
        transport = FixtureTransport()
        fetched_at = datetime.fromisoformat("2026-07-14T12:40:00+08:00")
        source = GGZYSource(
            transport=transport,
            request_interval=0,
            now=lambda: fetched_at,
        )
        task = TaskSpec(
            task_id="task-ggzy-001",
            query="查找安徽省计算设备采购公告",
            topic="计算设备",
            regions=["安徽省"],
            keywords=["计算设备"],
            time_range_start="2026-07-10T00:00:00+08:00",
            time_range_end="2026-07-14T23:59:59+08:00",
        )

        notices = await source.collect(task, {})

        self.assertEqual(len(notices), 2)
        self.assertTrue(all(isinstance(notice, TenderNotice) for notice in notices))
        post_calls = [call for call in transport.calls if call[0] == "POST"]
        self.assertEqual([call[2]["PAGENUMBER"] for call in post_calls], ["1", "2"])
        self.assertEqual(post_calls[0][2]["FINDTXT"], "计算设备")
        self.assertEqual(post_calls[0][2]["DEAL_PROVINCE"], "340000")
        self.assertEqual(post_calls[0][2]["TIMEBEGIN"], "2026-07-10")
        self.assertEqual(post_calls[0][2]["TIMEEND"], "2026-07-14")
        self.assertEqual(post_calls[0][2]["DEAL_TIME"], "06")
        self.assertEqual(post_calls[0][2]["DEAL_STAGE"], "0001")
        self.assertEqual(notices[1].purchaser, "某区政务服务管理局")

    async def test_collect_follows_public_embedded_original_without_hiding_provenance(self) -> None:
        class EmbeddedTransport:
            async def request(
                self,
                method: str,
                url: str,
                *,
                data: dict[str, str] | None,
                headers: dict[str, str],
                timeout: float,
            ) -> GGZYHTTPResponse:
                if method == "POST":
                    fixture = "search_embedded.json"
                    content_type = "application/json; charset=utf-8"
                elif "origin.example.gov.cn" in url:
                    fixture = "detail_embedded_origin.html"
                    content_type = "text/html; charset=utf-8"
                else:
                    fixture = "detail_embedded_wrapper.html"
                    content_type = "text/html; charset=utf-8"
                return GGZYHTTPResponse(
                    status=200,
                    url=url,
                    body=(FIXTURES / fixture).read_bytes(),
                    headers={"content-type": content_type},
                )

        fetched_at = datetime.fromisoformat("2026-07-14T12:45:00+08:00")
        source = GGZYSource(
            transport=EmbeddedTransport(),
            request_interval=0,
            now=lambda: fetched_at,
        )
        task = TaskSpec(
            task_id="task-ggzy-embedded",
            query="四川省公共服务平台采购",
            topic="公共服务平台",
            regions=["四川省"],
            keywords=["公共服务平台"],
            time_range_start="2026-07-14T00:00:00+08:00",
            time_range_end="2026-07-14T23:59:59+08:00",
        )

        notices = await source.collect(task, {})

        self.assertEqual(len(notices), 1)
        self.assertEqual(
            str(notices[0].source.source_url),
            "https://www.ggzy.gov.cn/information/deal/html/a/510000/0201/20260714/embedded001.html",
        )
        self.assertEqual(
            str(notices[0].source.canonical_notice_url),
            "https://origin.example.gov.cn/notices/embedded001.html",
        )
        self.assertIn("升级、部署和运维服务", notices[0].core_content)
        extracted_evidence = {
            item.field_path: str(item.source_url) for item in notices[0].evidence
        }
        evidence_by_field = {
            item.field_path: item for item in notices[0].evidence
        }
        self.assertEqual(
            extracted_evidence["purchaser"],
            "https://origin.example.gov.cn/notices/embedded001.html",
        )
        self.assertEqual(
            extracted_evidence["region"],
            "https://www.ggzy.gov.cn/information/pubTradingInfo/getTradList",
        )
        self.assertEqual(
            extracted_evidence["source.original_source_name"],
            "https://www.ggzy.gov.cn/information/pubTradingInfo/getTradList",
        )
        self.assertEqual(
            evidence_by_field["region"].quote,
            '{"province":"四川省"}',
        )
        self.assertEqual(
            evidence_by_field["source.original_source_name"].quote,
            '{"platform":"某省公共资源交易服务中心"}',
        )
        self.assertIn(
            '"source_notice_id":"embedded001"',
            evidence_by_field["region"].locator,
        )
        self.assertIn(
            '"PAGENUMBER":"1"',
            evidence_by_field["region"].locator,
        )
        self.assertEqual(
            str(notices[0].attachments[0].url),
            "https://origin.example.gov.cn/files/%E9%87%87%E8%B4%AD%E9%9C%80%E6%B1%82%E4%B9%A6.docx",
        )

    async def test_empty_search_returns_no_notices_without_detail_requests(self) -> None:
        class EmptyTransport:
            def __init__(self) -> None:
                self.calls = 0

            async def request(
                self,
                method: str,
                url: str,
                *,
                data: dict[str, str] | None,
                headers: dict[str, str],
                timeout: float,
            ) -> GGZYHTTPResponse:
                self.calls += 1
                return GGZYHTTPResponse(
                    status=200,
                    url=url,
                    body=(FIXTURES / "search_empty.json").read_bytes(),
                    headers={"content-type": "application/json; charset=utf-8"},
                )

        transport = EmptyTransport()
        source = GGZYSource(transport=transport, request_interval=0)
        task = TaskSpec(
            task_id="task-ggzy-empty",
            query="查询无结果主题",
            topic="无结果主题",
            keywords=["无结果主题"],
            time_range_start="2026-07-14T00:00:00+08:00",
            time_range_end="2026-07-14T23:59:59+08:00",
        )

        notices = await source.collect(task, {})

        self.assertEqual(notices, [])
        self.assertEqual(transport.calls, 1)

    async def test_timeout_is_reported_without_bypassing_the_source(self) -> None:
        class TimeoutTransport:
            async def request(
                self,
                method: str,
                url: str,
                *,
                data: dict[str, str] | None,
                headers: dict[str, str],
                timeout: float,
            ) -> GGZYHTTPResponse:
                raise TimeoutError("fixture timeout")

        source = GGZYSource(
            transport=TimeoutTransport(),
            retries=0,
            request_interval=0,
        )
        task = TaskSpec(
            task_id="task-ggzy-timeout",
            query="查询计算设备公告",
            topic="计算设备",
            keywords=["计算设备"],
        )

        with self.assertRaises(GGZYTimeoutError):
            await source.collect(task, {})

    async def test_single_ended_time_windows_keep_the_open_side(self) -> None:
        class CapturingEmptyTransport:
            def __init__(self) -> None:
                self.forms: list[dict[str, str]] = []

            async def request(
                self,
                method: str,
                url: str,
                *,
                data: dict[str, str] | None,
                headers: dict[str, str],
                timeout: float,
            ) -> GGZYHTTPResponse:
                assert data is not None
                self.forms.append(data)
                return GGZYHTTPResponse(
                    status=200,
                    url=url,
                    body=(FIXTURES / "search_empty.json").read_bytes(),
                    headers={"content-type": "application/json; charset=utf-8"},
                )

        transport = CapturingEmptyTransport()
        source = GGZYSource(
            transport=transport,
            request_interval=0,
            now=lambda: datetime.fromisoformat("2026-07-14T13:00:00+08:00"),
        )
        await source.collect(
            TaskSpec(
                task_id="task-start-only",
                query="开始时间后的计算设备公告",
                topic="计算设备",
                keywords=["计算设备"],
                time_range_start="2026-07-10T00:00:00+08:00",
            ),
            {},
        )
        await source.collect(
            TaskSpec(
                task_id="task-end-only",
                query="结束时间前的计算设备公告",
                topic="计算设备",
                keywords=["计算设备"],
                time_range_end="2026-07-10T23:59:59+08:00",
            ),
            {},
        )

        self.assertEqual(transport.forms[0]["TIMEEND"], "2026-07-14")
        self.assertEqual(transport.forms[1]["TIMEBEGIN"], "2000-01-01")

    async def test_region_filter_rejects_an_out_of_region_result(self) -> None:
        transport = FixtureTransport()
        source = GGZYSource(transport=transport, request_interval=0)
        task = TaskSpec(
            task_id="task-region-filter",
            query="查找上海市计算设备公告",
            topic="计算设备",
            regions=["上海市"],
            keywords=["计算设备"],
            time_range_start="2026-07-10T00:00:00+08:00",
            time_range_end="2026-07-14T23:59:59+08:00",
        )

        notices = await source.collect(task, {})

        self.assertEqual(notices, [])


if __name__ == "__main__":
    unittest.main()
