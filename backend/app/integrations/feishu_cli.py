"""Local operator CLI for the Feishu Bitable delivery channel.

Run from ``backend``:
    python -m app.integrations.feishu_cli status
    python -m app.integrations.feishu_cli check
    python -m app.integrations.feishu_cli flush
    python -m app.integrations.feishu_cli outbox
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .feishu import FeishuBitableClient, FeishuConfig, FeishuDeliveryService, PROVIDER_ID
from ..storage.repository import Repository


def _write(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    parser = argparse.ArgumentParser(description="BidRadar-X 飞书多维表格通道")
    parser.add_argument(
        "command",
        choices=("status", "check", "flush", "outbox"),
        help="查看配置、检查权限、推送待发事件或查看 Outbox",
    )
    args = parser.parse_args()
    config = FeishuConfig.from_env()
    repository = Repository()

    if args.command == "status":
        _write(config.safe_status())
        return 0
    if args.command == "outbox":
        rows = repository.list_external_deliveries(provider=PROVIDER_ID)
        _write({
            "count": len(rows),
            "items": [
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"payload"}
                }
                for row in rows
            ],
        })
        return 0
    if not config.enabled:
        _write(config.safe_status())
        return 2
    if args.command == "check":
        client = FeishuBitableClient(config)
        fields = client.list_fields()
        client.validate_fields()
        _write({
            "ok": True,
            "field_count": len(fields),
            "required_fields": list(config.field_map.values()),
        })
        return 0
    if args.command == "flush":
        _write(FeishuDeliveryService(repository, config=config).flush_due())
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
