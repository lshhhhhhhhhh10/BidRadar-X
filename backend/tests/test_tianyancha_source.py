from __future__ import annotations

from datetime import datetime, timezone
import unittest

from app.sources.tianyancha import (
    SEARCH_URL,
    TianyanchaAuthenticationError,
    TianyanchaHTTPResponse,
    TianyanchaSource,
)


class FakeTransport:
    def __init__(self, response: TianyanchaHTTPResponse) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def get(self, url: str, *, params: dict, headers: dict, timeout: float):
        self.calls.append(
            {"url": url, "params": params, "headers": headers, "timeout": timeout}
        )
        return self.response


class NoopSpendGuard:
    def charge(self, **kwargs):
        return None


TASK = {
    "task_id": "task-tyc",
    "query": "安徽省服务器采购",
    "topic": "服务器采购",
    "regions": ["安徽省"],
    "keywords": ["服务器"],
}


class TianyanchaSourceTest(unittest.IsolatedAsyncioTestCase):
    async def test_missing_token_is_rejected(self) -> None:
        with self.assertRaises(TianyanchaAuthenticationError):
            await TianyanchaSource(token="").collect(TASK)

    async def test_collects_and_normalizes_authorized_results(self) -> None:
        transport = FakeTransport(
            TianyanchaHTTPResponse(
                url=SEARCH_URL,
                status_code=200,
                payload={
                    "error_code": 0,
                    "reason": "ok",
                    "result": {
                        "total": 1,
                        "items": [
                            {
                                "uuid": "bid-001",
                                "title": "高性能服务器采购公告",
                                "publishTime": "1784246400000",
                                "bidUrl": "https://m.tianyancha.com/app/h5/bid/bid-001",
                                "link": "https://example.gov.cn/notices/bid-001",
                                "content": "<div><p>采购服务器 20 台</p></div>",
                                "purchaser": "示例采购单位",
                                "type": "招标公告",
                                "province": "安徽",
                            }
                        ],
                    },
                },
            )
        )
        source = TianyanchaSource(
            token="secret-token",
            transport=transport,
            now=lambda: datetime(2026, 7, 17, tzinfo=timezone.utc),
            spend_guard=NoopSpendGuard(),
        )

        notices = await source.collect(TASK)

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].notice_id, "tyc-bid-001")
        self.assertEqual(notices[0].notice_type, "tender")
        self.assertEqual(notices[0].purchaser, "示例采购单位")
        self.assertEqual(notices[0].region, "安徽")
        self.assertIn("采购服务器 20 台", notices[0].core_content)
        self.assertEqual(transport.calls[0]["url"], SEARCH_URL)
        self.assertEqual(transport.calls[0]["headers"]["Authorization"], "secret-token")
        self.assertNotIn("secret-token", transport.calls[0]["params"])
        self.assertEqual(transport.calls[0]["params"]["province"], "安徽")

    async def test_api_permission_error_is_authentication_failure(self) -> None:
        transport = FakeTransport(
            TianyanchaHTTPResponse(
                url=SEARCH_URL,
                status_code=200,
                payload={"error_code": 300005, "reason": "无权限访问此api"},
            )
        )
        source = TianyanchaSource(token="bad-token", transport=transport, spend_guard=NoopSpendGuard())

        with self.assertRaises(TianyanchaAuthenticationError):
            await source.collect(TASK)


if __name__ == "__main__":
    unittest.main()
