from __future__ import annotations

import base64
from datetime import datetime, timezone
from io import BytesIO
import unittest

from pypdf import PdfWriter

from app.sources.cmcc_b2b import CMCCHTTPResponse, CMCCB2BSource, DETAIL_URL, LIST_URL


def _pdf_base64() -> str:
    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.write(buffer)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url: str, *, payload: dict, timeout: float) -> CMCCHTTPResponse:
        self.calls.append((url, payload))
        if url == LIST_URL:
            data = {
                "content": [
                    {
                        "id": "1001",
                        "uuid": "notice-uuid",
                        "name": "服务器设备采购公告",
                        "publishDate": "2026-07-17T09:00:00",
                        "publishType": "PROCUREMENT",
                        "publishOneType": "PROCUREMENT",
                        "companyTypeName": "北京市",
                    },
                    {
                        "id": "1002",
                        "uuid": "closed-uuid",
                        "name": "服务器项目中标公告",
                        "publishDate": "2026-07-17T09:00:00",
                    },
                ]
            }
        elif url == DETAIL_URL:
            data = {
                "contentType": "pdf",
                "noticeContent": _pdf_base64(),
                "projectName": "服务器设备采购",
                "companyName": "中国移动测试公司",
                "backDate": "2026-07-28T09:00:00",
            }
        else:
            raise AssertionError(url)
        return CMCCHTTPResponse(url=url, status_code=200, payload={"code": 0, "data": data})


TASK = {
    "task_id": "task-cmcc",
    "query": "最近三个月服务器采购",
    "topic": "服务器采购",
    "regions": ["北京市"],
    "keywords": ["服务器"],
}


class CMCCB2BSourceTest(unittest.IsolatedAsyncioTestCase):
    async def test_collects_public_notice_and_embedded_pdf_without_login(self) -> None:
        transport = FakeTransport()
        source = CMCCB2BSource(
            transport=transport,
            now=lambda: datetime(2026, 7, 17, tzinfo=timezone.utc),
        )

        notices = await source.collect(TASK)

        self.assertEqual(len(notices), 1)
        notice = notices[0]
        self.assertEqual(notice.notice_id, "cmcc-1001")
        self.assertEqual(notice.notice_type, "tender")
        self.assertEqual(notice.purchaser, "中国移动测试公司")
        self.assertEqual(notice.region, "北京市")
        self.assertEqual(len(notice.attachments), 1)
        self.assertEqual(notice.attachments[0].media_type, "application/pdf")
        self.assertFalse(source.metadata["requires_login"])
        self.assertEqual([call[0] for call in transport.calls], [LIST_URL, DETAIL_URL])


if __name__ == "__main__":
    unittest.main()
