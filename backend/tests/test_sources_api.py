from __future__ import annotations

import os
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class SourcesAPITest(TestCase):
    def test_lists_all_required_source_categories(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            response = TestClient(app).get("/api/sources")

        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        categories = {item["category"] for item in items}
        self.assertTrue(
            {"government", "enterprise", "commercial", "overseas", "news"}.issubset(categories)
        )
        sam_gov = next(item for item in items if item["id"] == "sam-gov")
        self.assertEqual(sam_gov["status"], "needs_auth")
        self.assertTrue(sam_gov["requires_auth"])
        self.assertFalse(any(item["id"] == "jianyu" for item in items))
        cmcc = next(item for item in items if item["id"] == "cmcc-b2b")
        self.assertEqual(cmcc["status"], "ready")
        self.assertFalse(cmcc["requires_auth"])
        self.assertFalse(cmcc["authenticated_content"])
        self.assertIn("不计入", cmcc["contest_login_requirement"])
        ggzy = next(item for item in items if item["id"] == "ggzy-national")
        self.assertEqual(ggzy["name"], "全国公共资源交易平台")
        self.assertEqual(ggzy["status"], "ready")
        self.assertTrue(ggzy["adapter_registered"])
        self.assertFalse(ggzy["requires_auth"])
        tianyancha = next(item for item in items if item["id"] == "tianyancha-bids")
        self.assertEqual(tianyancha["status"], "needs_auth")
        for planned_id in ("ted-eu", "ctba-news"):
            planned = next(item for item in items if item["id"] == planned_id)
            self.assertEqual(planned["status"], "restricted")
            self.assertFalse(planned["adapter_registered"])

    def test_tianyancha_becomes_ready_without_exposing_token(self) -> None:
        with patch.dict(os.environ, {"BIDRADAR_TIANYANCHA_TOKEN": "private-token"}):
            response = TestClient(app).get("/api/sources")

        source = next(
            item for item in response.json()["items"] if item["id"] == "tianyancha-bids"
        )
        self.assertEqual(source["status"], "ready")
        self.assertNotIn("private-token", response.text)

    def test_sam_gov_becomes_ready_without_exposing_api_key(self) -> None:
        with patch.dict(os.environ, {"BIDRADAR_SAM_GOV_API_KEY": "private-sam-key"}):
            response = TestClient(app).get("/api/sources")

        source = next(item for item in response.json()["items"] if item["id"] == "sam-gov")
        self.assertEqual(source["status"], "ready")
        self.assertNotIn("private-sam-key", response.text)

    def test_local_user_can_connect_and_disconnect_without_echoing_secret(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BIDRADAR_TIANYANCHA_TOKEN", None)
            client = TestClient(app)
            connected = client.put(
                "/api/sources/tianyancha-bids/credential",
                json={"credential": "user-owned-secret-token"},
            )
            catalog = client.get("/api/sources")
            disconnected = client.delete("/api/sources/tianyancha-bids/credential")

            self.assertEqual(connected.status_code, 200)
            self.assertTrue(connected.json()["configured"])
            self.assertFalse(connected.json()["verified"])
            self.assertNotIn("user-owned-secret-token", connected.text)
            source = next(
                item for item in catalog.json()["items"] if item["id"] == "tianyancha-bids"
            )
            self.assertEqual(source["status"], "ready")
            self.assertEqual(disconnected.status_code, 200)
            self.assertNotIn("BIDRADAR_TIANYANCHA_TOKEN", os.environ)

    def test_credential_endpoint_rejects_unknown_sources_and_short_secrets(self) -> None:
        client = TestClient(app)
        unknown = client.put(
            "/api/sources/unknown/credential",
            json={"credential": "long-enough-value"},
        )
        too_short = client.put(
            "/api/sources/tianyancha-bids/credential",
            json={"credential": "short"},
        )

        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(too_short.status_code, 422)
