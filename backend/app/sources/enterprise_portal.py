from __future__ import annotations

from typing import Any


class EnterprisePortalSource:
    metadata = {
        "source_id": "enterprise-portal",
        "name": "企业采购门户",
        "authority": 0.82,
        "hit_rate": 0.72,
        "stability": 0.88,
        "cost": 0.25,
        "attempts": 11,
        "requires_login": False,
    }

    async def collect(self, task_spec: dict[str, Any], search_plan: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "source_id": self.metadata["source_id"],
                "source_name": self.metadata["name"],
                "url": "https://example.local/enterprise/gpu-cluster",
                "title": "安徽某制造企业GPU服务器集群采购",
                "published_at": "2026-07-10T16:00:00+08:00",
                "document_type": "dynamic_html",
                "notice_type": "tender",
                "project_code": "AHM-2026-GPU-03",
                "purchaser": "安徽某制造企业",
                "budget": 5600000,
                "deadline": "2026-08-06T17:00:00+08:00",
                "content": "<div>建设AI训练平台，采购8台GPU服务器、网络交换设备及集群管理软件，预算560万元。</div>",
            },
            {
                "source_id": self.metadata["source_id"],
                "source_name": self.metadata["name"],
                "url": "https://example.local/enterprise/ahu-server-mirror",
                "title": "安徽某高校高性能服务器采购项目",
                "published_at": "2026-07-08T10:15:00+08:00",
                "document_type": "html",
                "notice_type": "tender",
                "project_code": "AHU-2026-SRV-01",
                "purchaser": "安徽某高校",
                "budget": 3200000,
                "deadline": "2026-08-01T09:00:00+08:00",
                "content": "安徽某高校高性能服务器采购项目，采购机架式服务器及GPU计算节点，预算320万元，投标截止时间为2026年8月1日9时。",
            },
        ]
