import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from app.sources.jianyu import (
    JianyuAuthenticationError,
    JianyuAutomationNotAuthorizedError,
    JianyuLoginSession,
    JianyuParsingError,
    JianyuSessionError,
    JianyuSource,
    SESSION_STATE_ENV,
)


FIXTURES = Path(__file__).parent / "fixtures" / "jianyu"
DETAIL_URL = "https://anhui.jianyu360.cn/jybx/20260714_sanitized001.html"


class JianyuSessionTest(unittest.TestCase):
    def test_missing_session_fails_clearly(self) -> None:
        with self.assertRaisesRegex(JianyuSessionError, SESSION_STATE_ENV):
            JianyuLoginSession.from_environment({}, repository_root=FIXTURES.parents[3])

    def test_inline_storage_state_is_rejected(self) -> None:
        with self.assertRaisesRegex(JianyuSessionError, "external file"):
            JianyuLoginSession.from_environment(
                {SESSION_STATE_ENV: '{"cookies": [], "origins": []}'},
                repository_root=FIXTURES.parents[3],
            )

    def test_repository_storage_state_is_rejected_before_reading(self) -> None:
        in_repository = FIXTURES / "must-not-exist.json"
        with self.assertRaisesRegex(JianyuSessionError, "outside the repository"):
            JianyuLoginSession.from_environment(
                {SESSION_STATE_ENV: str(in_repository.resolve())},
                repository_root=FIXTURES.parents[3],
            )

    def test_sanitized_external_state_reference_can_be_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "cookies": [],
                        "origins": [
                            {
                                "origin": "https://www.jianyu360.cn",
                                "localStorage": [
                                    {"name": "test-session-marker", "value": "sanitized-placeholder"}
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            session = JianyuLoginSession.from_environment(
                {SESSION_STATE_ENV: str(state_path.resolve())},
                repository_root=FIXTURES.parents[3],
            )

            self.assertEqual(session.storage_state_path, state_path.resolve())

    def test_collect_never_returns_simulated_success(self) -> None:
        source = JianyuSource()
        with self.assertRaises(JianyuSessionError):
            asyncio.run(source.collect({}, {}))

        with tempfile.TemporaryDirectory() as directory:
            source = JianyuSource(JianyuLoginSession(Path(directory) / "external-state.json"))
            with self.assertRaisesRegex(JianyuAutomationNotAuthorizedError, "written"):
                asyncio.run(source.collect({}, {}))


class JianyuParserTest(unittest.TestCase):
    def test_authenticated_list_fixture_is_repeatable(self) -> None:
        records = JianyuSource.parse_notice_list(
            (FIXTURES / "list_authenticated.html").read_text(encoding="utf-8"),
            base_url="https://anhui.jianyu360.cn/search/",
        )

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["source_notice_id"], "sanitized-notice-001")
        self.assertEqual(records[0]["published_at"], "2026-07-14T09:30:00+08:00")
        self.assertEqual(records[1]["region"], "安徽 芜湖市")

    def test_authenticated_detail_fixture_extracts_contract_fields(self) -> None:
        notice = JianyuSource.parse_notice_detail(
            (FIXTURES / "detail_authenticated.html").read_text(encoding="utf-8"),
            url=DETAIL_URL,
        )

        self.assertEqual(notice["title"], "某高校计算设备采购公告")
        self.assertEqual(notice["published_at"], "2026-07-14T09:30:00+08:00")
        self.assertEqual(notice["project_code"], "TEST-2026-001")
        self.assertEqual(notice["purchaser"], "某高校")
        self.assertEqual(notice["budget"], "294000.0")
        self.assertEqual(notice["deadline"], "2026-07-30T17:00:00+08:00")
        self.assertEqual(notice["notice_type"], "tender")
        self.assertEqual(len(notice["attachments"]), 1)
        self.assertIn("计算设备及配套服务，具体技术要求", notice["content"])
        self.assertNotIn("联系人", notice["content"])

    def test_login_wall_fails_instead_of_parsing_partial_content(self) -> None:
        with self.assertRaisesRegex(JianyuAuthenticationError, "login-gated"):
            JianyuSource.parse_notice_detail(
                (FIXTURES / "detail_login_wall.html").read_text(encoding="utf-8"),
                url=DETAIL_URL,
            )

    def test_non_jianyu_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(JianyuParsingError, "Jianyu URLs"):
            JianyuSource.parse_notice_detail(
                (FIXTURES / "detail_authenticated.html").read_text(encoding="utf-8"),
                url="https://example.invalid/notices/1",
            )


if __name__ == "__main__":
    unittest.main()
