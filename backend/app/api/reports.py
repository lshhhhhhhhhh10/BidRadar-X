from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse

from .projects import load_project_summaries
from ..intelligence.task_title import summarized_task_title
from ..services.demo_shanghai_property import (
    DEMO_QUERY,
    demo_notices,
    demo_notices_for_scheduled_run,
)
from ..services.docx_publisher import DocxPublisher, build_report_filename
from ..services.publisher import REPORT_DIR
from ..services.source_failures import source_failure_reason
from ..storage.repository import Repository


router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/reports")
def list_reports() -> dict[str, list[dict]]:
    repository = Repository()
    items = repository.list_report_history()
    for item in items:
        item["report"] = _report_view(repository, item.pop("report", None))
        run = repository.get_run(item["run_id"])
        item["display_title"] = summarized_task_title(
            run.get("task_spec") if isinstance(run, dict) else None,
            fallback_query=item.get("query", ""),
        )
        item["projects"] = load_project_summaries(repository, run) if run else []
        item["sources"] = _source_outcomes(run)
    return {"items": items}


@router.delete("/reports/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def hide_report_history(run_id: str) -> Response:
    if not Repository().hide_report_run(run_id):
        raise HTTPException(status_code=404, detail="run not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/runs/{run_id}/report")
def get_run_report(run_id: str) -> dict:
    repository = Repository()
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return _report_view(repository, run.get("report"))


@router.get("/reports/{delivery_fingerprint}/download")
def download_report(delivery_fingerprint: str) -> FileResponse:
    """Compatibility route: download the first project document in a delivery."""

    return _download_delivery_document(delivery_fingerprint)


@router.get("/reports/{delivery_fingerprint}/documents/{document_id}/download")
def download_report_document(
    delivery_fingerprint: str,
    document_id: str,
) -> FileResponse:
    return _download_delivery_document(delivery_fingerprint, document_id)


def _download_delivery_document(
    delivery_fingerprint: str,
    document_id: str | None = None,
) -> FileResponse:
    if re.fullmatch(r"[0-9a-f]{64}", delivery_fingerprint) is None:
        raise HTTPException(status_code=400, detail="invalid report identifier")
    if document_id is not None and re.fullmatch(r"[0-9a-f]{16}", document_id) is None:
        raise HTTPException(status_code=400, detail="invalid document identifier")
    repository = Repository()
    delivery = repository.get_delivery(delivery_fingerprint)
    if delivery is None:
        raise HTTPException(status_code=404, detail="report not found")
    if delivery["status"] not in {"generated", "delivered"}:
        raise HTTPException(status_code=409, detail="report is not available")
    documents = _delivery_documents(repository, delivery)
    document = next(
        (
            item
            for item in documents
            if document_id is None or item["document_id"] == document_id
        ),
        None,
    )
    if document is None:
        raise HTTPException(status_code=409, detail="report artifact is invalid")
    report_path = _safe_docx_path(document.get("artifact_uri"))
    if report_path is None:
        raise HTTPException(status_code=409, detail="report artifact is invalid")
    if not report_path.is_file():
        raise HTTPException(status_code=410, detail="report file is missing")
    return FileResponse(
        report_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=str(document.get("filename") or report_path.name),
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
    artifact_path = _safe_artifact_path(delivery.get("artifact_uri"))
    documents = _delivery_documents(repository, delivery)
    if artifact_path is None or not artifact_path.is_file() or not documents:
        return {
            **base,
            "status": "missing",
            "delivery_fingerprint": fingerprint,
            "filename": delivery.get("artifact_uri"),
            "documents": [],
            "document_count": 0,
        }
    available_documents = [item for item in documents if item["status"] == "available"]
    status = "available" if len(available_documents) == len(documents) else "missing"
    first_document = documents[0]
    return {
        **base,
        "status": status,
        "delivery_fingerprint": fingerprint,
        "filename": first_document["filename"],
        "download_url": f"/api/reports/{fingerprint}/download",
        "documents": documents,
        "document_count": len(documents),
    }


def _source_outcomes(run: object) -> list[dict]:
    if not isinstance(run, dict):
        return []
    outcomes: list[dict] = []
    for source in run.get("selected_sources", []):
        if not isinstance(source, dict):
            continue
        outcome = {
                "source_id": source.get("source_id") or source.get("id"),
                "name": source.get("name") or source.get("source_id") or "未知来源",
                "status": source.get("collection_status") or "not_attempted",
                "record_count": int(source.get("record_count") or 0),
                "requires_login": bool(source.get("requires_login") or source.get("requires_auth")),
                "attempt_count": int(source.get("attempt_count") or 0),
            }
        if outcome["status"] == "failed":
            outcome["failure_reason"] = (
                source.get("failure_reason") or source_failure_reason(source)
            )
        outcomes.append(outcome)
    return outcomes


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


def _delivery_documents(repository: Repository, delivery: dict) -> list[dict]:
    artifact_path = _safe_artifact_path(delivery.get("artifact_uri"))
    if artifact_path is None or not artifact_path.is_file():
        return []
    fingerprint = str(delivery.get("delivery_fingerprint") or "")
    if artifact_path.suffix.lower() == ".docx":
        document_id = sha256(artifact_path.name.encode("utf-8")).hexdigest()[:16]
        return [{
            "document_id": document_id,
            "project_id": "legacy",
            "project_title": "历史项目报告",
            "filename": _download_filename(repository, delivery, artifact_path.name),
            "artifact_uri": artifact_path.name,
            "download_url": f"/api/reports/{fingerprint}/download",
            "notice_count": 0,
            "change_type": "legacy",
            "is_new": False,
            "generated_at": delivery.get("generated_at") or delivery.get("created_at"),
            "status": "available",
        }]
    try:
        manifest = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(manifest, dict) or manifest.get("delivery_fingerprint") != fingerprint:
        return []
    raw_documents = manifest.get("documents")
    if not isinstance(raw_documents, list):
        return []
    documents: list[dict] = []
    for raw in raw_documents:
        if not isinstance(raw, dict):
            continue
        document_id = raw.get("document_id")
        if not isinstance(document_id, str) or re.fullmatch(r"[0-9a-f]{16}", document_id) is None:
            continue
        document_path = _safe_docx_path(raw.get("artifact_uri"))
        if document_path is None:
            continue
        public_filename = raw.get("filename")
        if (
            not isinstance(public_filename, str)
            or Path(public_filename).name != public_filename
            or not public_filename.lower().endswith(".docx")
        ):
            public_filename = document_path.name
        documents.append({
            "document_id": document_id,
            "project_id": str(raw.get("project_id") or ""),
            "project_title": str(raw.get("project_title") or "未命名项目"),
            "filename": public_filename,
            "artifact_uri": document_path.name,
            "download_url": (
                f"/api/reports/{fingerprint}/documents/{document_id}/download"
            ),
            "notice_count": int(raw.get("notice_count") or 0),
            "change_type": str(raw.get("change_type") or "material_change"),
            "is_new": bool(raw.get("is_new", True)),
            "generated_at": raw.get("generated_at") or manifest.get("generated_at"),
            "status": "available" if document_path.is_file() else "missing",
        })
    return documents


def _safe_artifact_path(artifact_uri: object) -> Path | None:
    if not isinstance(artifact_uri, str) or not artifact_uri:
        return None
    artifact = Path(artifact_uri)
    if artifact.name != artifact_uri or artifact.suffix.lower() not in {".docx", ".json"}:
        return None
    root = REPORT_DIR.resolve()
    candidate = (root / artifact_uri).resolve()
    if candidate.parent != root:
        return None
    return candidate


def _safe_docx_path(artifact_uri: object) -> Path | None:
    candidate = _safe_artifact_path(artifact_uri)
    if candidate is None or candidate.suffix.lower() != ".docx":
        return None
    return candidate
