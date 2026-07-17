from __future__ import annotations

import asyncio
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from pypdf import PdfWriter

from app.intelligence.bidder_insights import build_bidder_insights
from app.intelligence.task_title import summarized_task_title
from app.schemas.tender import Attachment
from app.services.attachment_archive import AttachmentArchive, DownloadedPDF
from tests.integration_support import make_notice


def pdf_bytes() -> bytes:
    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.write(buffer)
    return buffer.getvalue()


class AttachmentArchiveTest(unittest.TestCase):
    def test_archives_pdf_to_a_named_local_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            notice = make_notice(
                source_id="ccgp",
                source_name="中国政府采购网",
                source_url="https://www.ccgp.gov.cn/notice/001",
                marker="a",
                attachment_url="https://www.ccgp.gov.cn/files/001.pdf",
            )
            archive = AttachmentArchive(
                root=Path(directory),
                fetcher=lambda url: DownloadedPDF(pdf_bytes(), url, "application/pdf"),
                clock=lambda: datetime(2026, 7, 17, 20, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )

            notices, archived, failed = asyncio.run(
                archive.archive_notices([notice], collection_name="上海/服务器采购")
            )

            attachment = notices[0].attachments[0]
            self.assertEqual((archived, failed), (1, 0))
            self.assertEqual(attachment.archive_status, "available")
            self.assertTrue(Path(attachment.local_path or "").is_file())
            self.assertEqual(Path(attachment.local_path or "").suffix, ".pdf")
            self.assertNotIn("/服务器", Path(attachment.local_path or "").parent.name)
            self.assertEqual(len(attachment.content_sha256 or ""), 64)

    def test_marks_landing_page_without_pdf_as_source_without_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            notice = make_notice(
                source_id="ccgp",
                source_name="中国政府采购网",
                source_url="https://www.ccgp.gov.cn/notice/001",
                marker="b",
                attachment_url="https://www.ccgp.gov.cn/download?id=1",
            )
            archive = AttachmentArchive(
                root=Path(directory),
                fetcher=lambda url: DownloadedPDF(b"<html>notice has no attachment</html>", url, "text/html"),
            )

            notices, archived, failed = asyncio.run(
                archive.archive_notices([notice], collection_name="服务器采购")
            )

            self.assertEqual((archived, failed), (0, 0))
            self.assertEqual(notices[0].attachments[0].archive_status, "unsupported")
            self.assertEqual(notices[0].attachments[0].archive_error, "source_has_no_pdf")
            self.assertEqual(list(Path(directory).rglob("*.pdf")), [])

    def test_resolves_customs_landing_page_to_public_attachment_api(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            landing_url = "http://hgcg.customs.gov.cn/portalweb/bid/detail?id=article-1"
            notice = make_notice(
                source_id="ccgp",
                source_name="中国政府采购网",
                source_url="https://www.ccgp.gov.cn/notice/001",
                marker="customs",
                attachment_url=landing_url,
            )

            def fetch(url: str) -> DownloadedPDF:
                if "/attachment/list?" in url:
                    payload = {"data": [{"fileName": "server.pdf", "originFileName": "招标文件.pdf"}]}
                    return DownloadedPDF(json.dumps(payload).encode(), url, "application/json")
                if "/attachment/download?" in url:
                    return DownloadedPDF(pdf_bytes(), url, "application/pdf")
                return DownloadedPDF(b"<html><div id='app'></div></html>", url, "text/html")

            archive = AttachmentArchive(root=Path(directory), fetcher=fetch)
            notices, archived, failed = asyncio.run(
                archive.archive_notices([notice], collection_name="服务器采购")
            )

            attachment = notices[0].attachments[0]
            self.assertEqual((archived, failed), (1, 0))
            self.assertEqual(attachment.archive_status, "available")
            self.assertTrue(Path(attachment.local_path or "").is_file())

    def test_marks_login_wall_as_access_denied_instead_of_no_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            notice = make_notice(
                source_id="ccgp",
                source_name="中国政府采购网",
                source_url="https://www.ccgp.gov.cn/notice/001",
                marker="d",
                attachment_url="https://example.gov.cn/download?id=1",
            )
            archive = AttachmentArchive(
                root=Path(directory),
                fetcher=lambda url: DownloadedPDF(b"<html>\xe8\xaf\xb7\xe5\x85\x88\xe7\x99\xbb\xe5\xbd\x95</html>", url, "text/html"),
            )

            notices, archived, failed = asyncio.run(
                archive.archive_notices([notice], collection_name="服务器采购")
            )

            attachment = notices[0].attachments[0]
            self.assertEqual((archived, failed), (0, 1))
            self.assertEqual(attachment.archive_status, "failed")
            self.assertEqual(attachment.archive_error, "access_denied")

    def test_builds_evidence_bound_bidder_metrics_and_contacts(self) -> None:
        notice = make_notice(
            source_id="ccgp",
            source_name="中国政府采购网",
            source_url="https://www.ccgp.gov.cn/notice/001",
            marker="c",
        ).model_copy(
            update={
                "core_content": (
                    "申请人的资格要求：具有电子与智能化工程专业承包资质。\n"
                    "投标保证金：人民币 5 万元。\n"
                    "评标办法：综合评分法。\n"
                    "项目联系人：张三 电话：13800138000。"
                ),
                "attachments": [
                    Attachment(
                        attachment_id="pdf-c",
                        name="招标文件.pdf",
                        url="https://www.ccgp.gov.cn/files/c.pdf",
                        archive_status="available",
                        local_path="/tmp/c.pdf",
                        extracted_text="合同履行期限：签订合同后 30 日内完成交付。",
                    )
                ],
            }
        )

        result = build_bidder_insights([notice])

        by_key = {item["key"]: item for item in result["items"]}
        self.assertIn("电子与智能化", by_key["qualification"]["value"])
        self.assertIn("5 万元", by_key["bond"]["value"])
        self.assertIn("30 日", by_key["duration"]["value"])
        self.assertEqual(result["contacts"][0]["name"], "张三")
        self.assertEqual(result["contacts"][0]["phone"], "13800138000")

    def test_summarizes_history_title_from_normalized_intent(self) -> None:
        title = summarized_task_title(
            {"topic": "服务器采购公告", "regions": ["安徽省"]},
            fallback_query="查询全国服务器采购公告 a75ea12e-4c05-4470-ac34-123456789012",
        )
        self.assertEqual(title, "安徽省 · 服务器采购")
        self.assertNotIn("a75ea", title)

    def test_history_title_keeps_available_time_region_and_topic(self) -> None:
        title = summarized_task_title(
            {"topic": "充电桩", "regions": []},
            fallback_query="请查询最近3个月上海市充电桩招标信息",
        )

        self.assertEqual(title, "最近3个月 · 上海市 · 充电桩采购")


if __name__ == "__main__":
    unittest.main()
