from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

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
    delivery = Repository().get_delivery(delivery_fingerprint)
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
        "filename": report_path.name,
        "download_url": f"/api/reports/{fingerprint}/download",
    }


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
