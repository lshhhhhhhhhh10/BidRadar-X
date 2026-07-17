from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from docx import Document
from fastapi.testclient import TestClient

from app.ai.client import StructuredAIClient
from app.ai.config import AISettings, clear_runtime_api_key
from app.ai.prompts import INTENT_PROMPT
from app.main import app
from app.services.docx_publisher import DocxPublisher
from tests.integration_support import make_notice


class AIPipelineTest(unittest.TestCase):
    def tearDown(self) -> None:
        clear_runtime_api_key()

    def test_structured_client_validates_json_and_audits_without_secret(self) -> None:
        captured: dict[str, object] = {}

        def transport(request, timeout):
            captured["timeout"] = timeout
            captured["authorization"] = request.get_header("Authorization")
            captured["url"] = request.full_url
            payload = json.loads(request.data.decode("utf-8"))
            captured["response_format"] = payload["response_format"]
            captured["system_message"] = payload["messages"][0]["content"]
            return {
                "id": "resp-test",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                    {
                                        "topic": "服务器",
                                        "regions": ["上海市"],
                                        "keywords": ["服务器", "计算节点"],
                                        "exclusions": [],
                                        "time_range_start": None,
                                        "time_range_end": None,
                                        "confidence": 0.96,
                                        "interpretation": "检索上海服务器采购公告",
                                    },
                                    ensure_ascii=False,
                                ),
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            }

        secret = "test-secret-this-must-never-enter-audit"
        settings = AISettings(
            provider="zhipu",
            api_key=secret,
            base_url="https://open.bigmodel.cn/api/paas/v4",
            model="glm-test",
            protocol="chat_completions_json",
            timeout_seconds=12,
            enabled=True,
        )
        result = StructuredAIClient(settings=settings, transport=transport).complete(
            INTENT_PROMPT,
            {"query": "上海服务器采购"},
        )

        self.assertIsNotNone(result.value)
        self.assertEqual(result.value.topic, "服务器")
        self.assertEqual(result.audit["status"], "completed")
        self.assertEqual(result.audit["input_tokens"], 100)
        self.assertNotIn(secret, json.dumps(result.audit, ensure_ascii=False))
        self.assertEqual(captured["authorization"], f"Bearer {secret}")
        self.assertEqual(captured["response_format"], {"type": "json_object"})
        self.assertIn("time_range_start", captured["system_message"])
        self.assertEqual(
            captured["url"],
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        )

    def test_invalid_model_output_returns_safe_fallback_signal(self) -> None:
        settings = AISettings(
            provider="zhipu",
            api_key="sk-test-invalid-output",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            model="glm-test",
            protocol="chat_completions_json",
            timeout_seconds=12,
            enabled=True,
        )
        client = StructuredAIClient(
            settings=settings,
            transport=lambda request, timeout: {
                "id": "resp-invalid",
                "choices": [{"message": {"content": "not-json"}}],
            },
        )

        result = client.complete(INTENT_PROMPT, {"query": "服务器"})

        self.assertIsNone(result.value)
        self.assertEqual(result.audit["status"], "invalid_output")
        self.assertNotIn("not-json", json.dumps(result.audit))

    def test_local_backend_credential_enables_status_without_returning_key(self) -> None:
        with patch.dict(os.environ, {"BIDRADAR_AI_API_KEY": ""}, clear=False), TestClient(app) as client:
            before = client.get("/api/ai/status")
            self.assertEqual(before.status_code, 200)
            self.assertFalse(before.json()["enabled"])

            secret = "test-secret-local-backend-memory-only"
            connected = client.put("/api/ai/credential", json={"api_key": secret})
            self.assertEqual(connected.status_code, 200, connected.text)
            self.assertTrue(connected.json()["enabled"])
            self.assertNotIn(secret, connected.text)

            disconnected = client.delete("/api/ai/credential")
            self.assertEqual(disconnected.status_code, 200)
            self.assertFalse(disconnected.json()["enabled"])

    def test_docx_keeps_original_content_and_adds_evidenced_ai_section(self) -> None:
        notice = make_notice(
            source_id="public-a",
            source_name="公开来源 A",
            source_url="https://public-a.gov.cn/notices/real-001",
            marker="a",
        )
        ai_report = {
            "status": "generated",
            "executive_summary": "发现一条与服务器采购直接相关的公告。",
            "key_findings": [
                {"text": "公告采购服务器及配套服务。", "evidence_ids": ["ev-test"]}
            ],
            "notice_narratives": [
                {
                    "notice_id": notice.notice_id,
                    "summary": "建议核对采购需求附件与截止时间。",
                    "risk_points": ["截止时间需以原公告为准"],
                    "next_actions": ["打开原公告复核"],
                    "evidence_ids": ["ev-test"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as output_dir:
            report_path = DocxPublisher(Path(output_dir)).publish(
                "服务器采购",
                [notice],
                ai_report=ai_report,
            )
            document = Document(BytesIO(report_path.read_bytes()))

        all_text = "\n".join(
            [paragraph.text for paragraph in document.paragraphs]
            + [
                paragraph.text
                for table in document.tables
                for row in table.rows
                for cell in row.cells
                for paragraph in cell.paragraphs
            ]
        )
        self.assertIn("AI 辅助研判", all_text)
        self.assertIn("建议核对采购需求附件与截止时间", all_text)
        self.assertIn(notice.core_content, all_text)


if __name__ == "__main__":
    unittest.main()
