from __future__ import annotations

from typing import Any


class PublicPlatformSource:
    metadata = {
        "source_id": "public-platform",
        "name": "政府公共资源平台",
        "authority": 1.0,
        "hit_rate": 0.86,
        "stability": 0.92,
        "cost": 0.18,
        "attempts": 18,
        "requires_login": False,
    }

    async def collect(self, task_spec: dict[str, Any], search_plan: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "source_id": self.metadata["source_id"],
                "source_name": self.metadata["name"],
                "url": "https://example.local/public/ahu-server",
                "title": "安徽某高校高性能服务器采购项目招标公告",
                "published_at": "2026-07-08T09:30:00+08:00",
                "document_type": "html",
                "notice_type": "tender",
                "project_code": "AHU-2026-SRV-01",
                "purchaser": "安徽某高校",
                "budget": 3200000,
                "deadline": "2026-08-01T09:00:00+08:00",
                "content": "<main><h1>安徽某高校高性能服务器采购项目</h1><p>采购机架式服务器及GPU计算节点，预算320万元，投标截止时间为2026年8月1日9时。</p></main>",
            },
            {
                "source_id": self.metadata["source_id"],
                "source_name": self.metadata["name"],
                "url": "https://example.local/public/medical-storage",
                "title": "安徽某医院存储服务器扩容项目采购公告",
                "published_at": "2026-07-05T14:00:00+08:00",
                "document_type": "pdf",
                "notice_type": "tender",
                "project_code": "AHH-2026-STO-09",
                "purchaser": "安徽某医院",
                "budget": 980000,
                "deadline": "2026-07-28T14:30:00+08:00",
                "content": "采购两台存储服务器及配套磁盘阵列，预算98万元，投标截止时间2026年7月28日14时30分。",
            },
            {
                "source_id": self.metadata["source_id"],
                "source_name": self.metadata["name"],
                "url": "https://example.local/public/office-paper",
                "title": "安徽某单位办公用品采购公告",
                "published_at": "2026-07-02T10:00:00+08:00",
                "document_type": "html",
                "notice_type": "tender",
                "project_code": "AHO-2026-001",
                "purchaser": "安徽某单位",
                "budget": 120000,
                "deadline": "2026-07-20T10:00:00+08:00",
                "content": "<p>采购打印纸、文件夹等日常办公用品，不包含服务器设备。</p>",
            },
        ]
