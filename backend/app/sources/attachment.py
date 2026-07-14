from __future__ import annotations

from typing import Any


class AttachmentSource:
    """Placeholder seam for PDF, Office and scanned attachment acquisition."""

    async def fetch(self, url: str) -> dict[str, Any]:
        return {"url": url, "document_type": "pdf", "content": "模拟附件正文", "page_count": 1}
