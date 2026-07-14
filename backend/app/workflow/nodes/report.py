from __future__ import annotations

from typing import Any

from ...services.publisher import DeliveryPublishError, Publisher
from .common import step


def generate_report(state: dict[str, Any]) -> dict[str, Any]:
    any_source_succeeded = any(
        source.get("collection_status") == "success"
        for source in state.get("selected_sources", [])
    )
    publisher = Publisher()
    if any_source_succeeded:
        try:
            report = publisher.publish(state)
        except DeliveryPublishError as error:
            report = {
                "status": "failed",
                "delivery_type": None,
                "filename": None,
                "download_url": None,
                "historical_report": None,
                "format": "docx",
                "report_scope": "incremental",
                "notice_count": 0,
                "reused_artifact": False,
                "delivery_fingerprint": error.delivery_fingerprint,
                "error_type": type(error.__cause__).__name__,
                "error": str(error),
                **publisher.source_outcomes(state),
            }
    else:
        report = {
            "status": "failed",
            "delivery_type": None,
            "filename": None,
            "download_url": None,
            "historical_report": None,
            "format": "docx",
            "report_scope": "incremental",
            "notice_count": 0,
            "reused_artifact": False,
            **publisher.source_outcomes(state),
        }
    return {
        "report": report,
        "status": "completed" if report["status"] in {"generated", "no_change"} else "failed",
        "steps": step(state, "报告生成 Agent", "使用去重后的真实公告字段生成并回读验证 DOCX。", len(state["changes"]), 1 if report["status"] == "generated" else 0, "completed" if report["status"] in {"generated", "no_change"} else "warning"),
    }
