"""Remove page chrome and CSS leakage before showing notice summaries."""

from __future__ import annotations

from html.parser import HTMLParser
import re


_STYLE_BLOCK = re.compile(r"<(?:style|script|noscript)\b[^>]*>.*?</(?:style|script|noscript)>", re.I | re.S)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_CSS_RULE = re.compile(r"(?:^|\s)[.#]?[a-zA-Z][\w\s>+~:,.#\[\]=\"'-]{0,160}\{[^{}]{0,1800}\}", re.S)
_CSS_DECLARATION = re.compile(
    r"(?:font-family|font-size|font-weight|line-height|border|background|display|width|height|margin|padding|color|text-align)\s*:[^;{}]{0,180};?",
    re.I,
)


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if cleaned:
            self.parts.append(cleaned)


def sanitize_notice_text(value: str | None, *, limit: int = 8_000) -> str:
    text = str(value or "")[:2_000_000]
    text = _STYLE_BLOCK.sub(" ", text)
    text = _CSS_COMMENT.sub(" ", text)
    for _ in range(3):
        updated = _CSS_RULE.sub(" ", text)
        if updated == text:
            break
        text = updated
    text = _CSS_DECLARATION.sub(" ", text)
    parser = _VisibleText()
    try:
        parser.feed(text)
        parser.close()
        text = " ".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\\[a-zA-Z-]+\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ;{}")
    return text[:limit]


__all__ = ["sanitize_notice_text"]
