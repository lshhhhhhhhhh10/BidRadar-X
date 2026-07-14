from __future__ import annotations

from typing import Any


class CommercialPlatformSource:
    metadata = {
        "source_id": "commercial-platform",
        "name": "登录型商业标讯平台",
        "authority": 0.68,
        "hit_rate": 0.91,
        "stability": 0.64,
        "cost": 0.62,
        "attempts": 7,
        "requires_login": True,
        "session_status": "simulated_healthy",
    }

    async def collect(self, task_spec: dict[str, Any], search_plan: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "source_id": self.metadata["source_id"],
                "source_name": self.metadata["name"],
                "url": "https://example.local/commercial/medical-storage",
                "title": "安徽某医院存储服务器扩容项目采购公告",
                "published_at": "2026-07-05T15:20:00+08:00",
                "document_type": "html",
                "notice_type": "tender",
                "project_code": "AHH-2026-STO-09",
                "purchaser": "安徽某医院",
                "budget": 980000,
                "deadline": "2026-07-28T14:30:00+08:00",
                "content": "采购两台存储服务器及配套磁盘阵列，预算98万元，投标截止时间2026年7月28日14时30分。",
            }
        ]
