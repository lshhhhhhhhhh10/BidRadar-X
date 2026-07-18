from __future__ import annotations

from datetime import datetime, timezone
import unittest

from app.sources.sam_gov import (
    SAMGovAuthenticationError,
    SAMGovHTTPResponse,
    SAMGovSource,
)


class FakeTransport:
    def __init__(self, response: SAMGovHTTPResponse) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def get(self, url: str, *, params: dict, timeout: float) -> SAMGovHTTPResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.response


def task_spec() -> dict:
    return {
        "task_id": "sam-test",
        "query": "cloud computing opportunity",
        "topic": "cloud computing",
        "regions": [],
        "keywords": ["cloud"],
        "exclusions": [],
        "time_range_start": "2026-07-01T00:00:00+00:00",
        "time_range_end": "2026-07-17T00:00:00+00:00",
        "schedule": {"frequency": "once", "timezone": "Asia/Shanghai"},
    }


class SAMGovSourceTest(unittest.IsolatedAsyncioTestCase):
    async def test_requires_server_side_api_key(self) -> None:
        source = SAMGovSource(api_key="")
        with self.assertRaises(SAMGovAuthenticationError):
            await source.collect(task_spec(), {"query": "cloud"})

    async def test_collects_authenticated_opportunities(self) -> None:
        transport = FakeTransport(
            SAMGovHTTPResponse(
                url="https://api.sam.gov/opportunities/v2/search",
                status_code=200,
                payload={
                    "totalRecords": 1,
                    "opportunitiesData": [
                        {
                            "noticeId": "abc123",
                            "title": "Cloud platform operations support",
                            "solicitationNumber": "SOL-2026-42",
                            "fullParentPathName": "GENERAL SERVICES ADMINISTRATION",
                            "postedDate": "2026-07-12",
                            "type": "Solicitation",
                            "description": "Managed cloud platform and security operations.",
                            "uiLink": "https://sam.gov/opp/abc123/view",
                        }
                    ],
                },
            )
        )
        source = SAMGovSource(
            api_key="secret-test-key",
            transport=transport,
            now=lambda: datetime(2026, 7, 17, tzinfo=timezone.utc),
        )

        notices = await source.collect(task_spec(), {"query": "cloud", "sam_gov_limit": 10})

        self.assertEqual(len(notices), 1)
        notice = notices[0]
        self.assertEqual(notice.notice_id, "sam-abc123")
        self.assertEqual(notice.source.source_id, "sam-gov")
        self.assertIn("Managed cloud platform", notice.core_content)
        self.assertNotIn("secret-test-key", notice.model_dump_json())
        self.assertEqual(transport.calls[0]["params"]["api_key"], "secret-test-key")
        self.assertEqual(transport.calls[0]["params"]["postedFrom"], "07/01/2026")

    async def test_rejected_key_is_reported_as_authentication_error(self) -> None:
        transport = FakeTransport(
            SAMGovHTTPResponse(
                url="https://api.sam.gov/opportunities/v2/search",
                status_code=403,
                payload={"message": "forbidden"},
            )
        )
        source = SAMGovSource(api_key="bad-key", transport=transport)
        with self.assertRaises(SAMGovAuthenticationError):
            await source.collect(task_spec(), {"query": "cloud"})


if __name__ == "__main__":
    unittest.main()
