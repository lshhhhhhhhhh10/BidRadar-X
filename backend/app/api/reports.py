from __future__ import annotations

from datetime import datetime
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..services.demo_shanghai_property import (
    DEMO_QUERY,
    demo_notices,
    demo_notices_for_scheduled_run,
)
from ..services.docx_publisher import DocxPublisher, build_report_filename
from ..services.publisher import REPORT_DIR
from ..storage.repository import Repository


router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/reports")
def list_reports() -> dict[str, list[dict]]:
    repository = Repository()
    items = repository.list_report_history()
    for item in items:
        item["report"] = _report_view(repository, item.pop("report", None))
    return {"items": items}


@router.get("/runs/{run_id}/report")
def get_run_report(run_id: str) -> dict:
    repository = Repository()
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return _report_view(repository, run.get("report"))


@router.get("/reports/{delivery_fingerprint}/download")
def download_report(delivery_fingerprint: str) -> FileResponse:
    if re.fullmatch(r"[0-9a-f]{64}", delivery_fingerprint) is None:
        raise HTTPException(status_code=400, detail="invalid report identifier")
    repository = Repository()
    delivery = repository.get_delivery(delivery_fingerprint)
    if delivery is None:
        raise HTTPException(status_code=404, detail="report not found")
    if delivery["status"] not in {"generated", "delivered"}:
        raise HTTPException(status_code=409, detail="report is not available")
    report_path = _safe_report_path(delivery.get("artifact_uri"))
    if report_path is None:
        raise HTTPException(status_code=409, detail="report artifact is invalid")
    if not report_path.is_file():
        raise HTTPException(status_code=410, detail="report file is missing")
    return FileResponse(
        report_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=_download_filename(repository, delivery, report_path.name),
    )


@router.get("/demo/reports/shanghai-property/download")
def download_shanghai_property_demo_report() -> FileResponse:
    """Generate the judged demo report with the required timestamped filename."""

    generated_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    output_dir = REPORT_DIR / "demo"
    report_path = output_dir / build_report_filename(DEMO_QUERY, generated_at)
    if not report_path.is_file():
        try:
            report_path = DocxPublisher(
                output_dir=output_dir,
                clock=lambda: generated_at,
            ).publish(DEMO_QUERY, demo_notices(), report_scope="full")
        except FileExistsError:
            # A second browser click in the same minute reuses the immutable artifact.
            if not report_path.is_file():
                raise
    return FileResponse(
        report_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=report_path.name,
    )


@router.get("/demo/reports/shanghai-property/runs/{run_id}/download")
def download_shanghai_property_incremental_report(run_id: str) -> FileResponse:
    """Download the clean Word report containing only one run's additions."""

    run = demo_notices_for_scheduled_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="demo scheduled run not found")
    executed_at, notices = run
    if not notices:
        raise HTTPException(
            status_code=409,
            detail="本次运行没有新增公告，因此不生成重复报告。",
        )

    output_dir = REPORT_DIR / "demo" / "scheduled-runs" / run_id
    report_path = output_dir / build_report_filename(DEMO_QUERY, executed_at)
    if not report_path.is_file():
        try:
            report_path = DocxPublisher(
                output_dir=output_dir,
                clock=lambda: executed_at,
            ).publish(DEMO_QUERY, notices, report_scope="incremental")
        except FileExistsError:
            if not report_path.is_file():
                raise
    return FileResponse(
        report_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=report_path.name,
    )


def _report_view(repository: Repository, report: object) -> dict:
    if not isinstance(report, dict):
        return {"status": "not_generated"}
    fingerprint = report.get("delivery_fingerprint")
    delivery = (
        repository.get_delivery(fingerprint)
        if isinstance(fingerprint, str)
        else None
    )
    base = {
        "delivery_type": report.get("delivery_type"),
        "report_scope": report.get("report_scope"),
        "notice_count": report.get("notice_count", 0),
    }
    if report.get("status") == "failed" or (
        delivery is not None and delivery["status"] == "failed"
    ):
        return {
            **base,
            "status": "failed",
            "error": "报告生成失败，请重新运行任务。",
        }
    if delivery is None or report.get("status") != "generated":
        return {**base, "status": "not_generated"}
    report_path = _safe_report_path(delivery.get("artifact_uri"))
    if report_path is None or not report_path.is_file():
        return {
            **base,
            "status": "missing",
            "delivery_fingerprint": fingerprint,
            "filename": delivery.get("artifact_uri"),
        }
    return {
        **base,
        "status": "available",
        "delivery_fingerprint": fingerprint,
        "filename": _download_filename(repository, delivery, report_path.name),
        "download_url": f"/api/reports/{fingerprint}/download",
    }


def _download_filename(
    repository: Repository,
    delivery: dict,
    fallback: str,
) -> str:
    """Expose the competition filename while retaining unique internal storage names."""

    run = repository.get_run(delivery.get("run_id", ""))
    if not isinstance(run, dict) or not isinstance(run.get("query"), str):
        return fallback
    timestamp_value = delivery.get("generated_at") or delivery.get("created_at")
    if not isinstance(timestamp_value, str):
        return fallback
    try:
        timestamp = datetime.fromisoformat(timestamp_value)
    except ValueError:
        return fallback
    return build_report_filename(run["query"], timestamp)


def _safe_report_path(artifact_uri: object) -> Path | None:
    if not isinstance(artifact_uri, str) or not artifact_uri:
        return None
    artifact = Path(artifact_uri)
    if artifact.name != artifact_uri or artifact.suffix.lower() != ".docx":
        return None
    root = REPORT_DIR.resolve()
    candidate = (root / artifact_uri).resolve()
    if candidate.parent != root:
        return None
    return candidate
