from __future__ import annotations

import re
from html import unescape
from typing import Any


class DocumentParser:
    """Routes mixed document types into one normalized document shape."""

    def parse(self, document: dict[str, Any]) -> dict[str, Any]:
        kind = document.get("document_type", "html")
        content = document.get("content", "")
        if kind in {"html", "dynamic_html"}:
            content = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", content, flags=re.I | re.S)
            content = re.sub(r"<[^>]+>", " ", content)
            content = unescape(content)
        content = re.sub(r"\s+", " ", content).strip()
        return {
            **document,
            "content": content,
            "parser_route": {
                "html": "dom_text",
                "dynamic_html": "browser_dom",
                "pdf": "pdf_layout",
                "scan": "ocr_layout",
            }.get(kind, "plain_text"),
        }
