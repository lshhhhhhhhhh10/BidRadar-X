from __future__ import annotations

import unittest

from app.intelligence.text_sanitizer import sanitize_notice_text


class NoticeTextSanitizerTest(unittest.TestCase):
    def test_removes_css_and_keeps_announcement_facts(self) -> None:
        raw = """
        /* 固定样式-start */ table { width: 100% !important; border: 1px solid; }
        <style>.headline { font-size: 30px; }</style>
        <div><h1>采购公告</h1><p>预算金额 3409287 元，截止时间 2026年7月27日。</p></div>
        """

        cleaned = sanitize_notice_text(raw)

        self.assertNotIn("font-size", cleaned)
        self.assertNotIn("width:", cleaned)
        self.assertIn("采购公告", cleaned)
        self.assertIn("3409287", cleaned)


if __name__ == "__main__":
    unittest.main()
