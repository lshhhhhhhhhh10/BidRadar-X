from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import shutil
import time
from typing import Any
from zoneinfo import ZoneInfo

from ..schemas.tender import (
    EvidenceReference,
    RequirementFact,
    RequirementSection,
    TenderNotice,
)
from ..storage.database import DATA_DIR
from ..storage.repository import Repository
from .docx_publisher import DocxPublisher, build_report_filename


REPORT_DIR = DATA_DIR / "reports"


class DeliveryPublishError(RuntimeError):
    def __init__(self, delivery_fingerprint: str, cause: Exception) -> None:
        super().__init__(str(cause))
        self.delivery_fingerprint = delivery_fingerprint
        self.__cause__ = cause


class Publisher:
    """Workflow bridge for the validated DOCX publisher."""

    def publish(self, state: dict[str, Any]) -> dict[str, Any]:
        projects = list(state.get("projects", []))
        changes = list(state.get("changes", []))
        outcomes = self.source_outcomes(state)
        repository = Repository()
        historical = repository.latest_generated_delivery(state["task_id"])
        committed_snapshots = repository.load_project_snapshots(state["task_id"])
        if not changes and historical is not None:
            historical_report = None
            if historical.get("artifact_uri"):
                historical_report = {
                    "filename": historical["artifact_uri"],
                    "download_url": f"/api/reports/{historical['delivery_fingerprint']}/download",
                    "delivery_fingerprint": historical["delivery_fingerprint"],
                }
            return {
                "status": "no_change",
                "delivery_type": None,
                "filename": None,
                "download_url": None,
                "historical_report": historical_report,
                "format": "docx",
                "report_scope": "incremental",
                "notice_count": 0,
                "reused_artifact": False,
                "delivery_fingerprint": None,
                **outcomes,
            }

        changed_project_ids = {change["project_id"] for change in changes}
        report_projects = [
            project for project in projects if project["project_id"] in changed_project_ids
        ]
        report_scope = "full" if (
            historical is None
            and not committed_snapshots
            and all(change["type"] == "new_project" for change in changes)
        ) else "incremental"
        notices = self._deduplicated_notices(report_projects)
        delivery_fingerprint = self._delivery_fingerprint(
            state,
            report_scope=report_scope,
            report_projects=report_projects,
        )
        delivery_type = (
            "full_snapshot"
            if report_scope == "full"
            else (
                "new_project"
                if all(change["type"] == "new_project" for change in changes)
                else "material_change"
            )
        )
        acquired, _delivery = repository.reserve_delivery(
            task_id=state["task_id"],
            run_id=state["run_id"],
            delivery_type=delivery_type,
            delivery_fingerprint=delivery_fingerprint,
            changes=changes,
            project_stable_fingerprints=sorted(
                {project["project_stable_fingerprint"] for project in report_projects}
            ),
            notice_stable_fingerprints=sorted(
                {
                    document["notice"]["notice_stable_fingerprint"]
                    for project in report_projects
                    for document in project["documents"]
                }
            ),
        )
        reused_artifact = False
        if acquired:
            try:
                report_path, reused_artifact = self._publish_delivery_report(
                    query=state["query"],
                    notices=notices,
                    task_id=state["task_id"],
                    run_id=state["run_id"],
                    report_scope=report_scope,
                    delivery_fingerprint=delivery_fingerprint,
                )
            except Exception as error:
                repository.mark_delivery_failed(
                    delivery_fingerprint,
                    state["run_id"],
                    f"{type(error).__name__}: {error}",
                )
                raise DeliveryPublishError(delivery_fingerprint, error) from error
        else:
            report_path = self._wait_for_committed_artifact(
                repository,
                delivery_fingerprint,
            )
            reused_artifact = True
        return {
            "status": "generated",
            "delivery_type": delivery_type,
            "filename": report_path.name,
            "download_url": f"/api/reports/{delivery_fingerprint}/download",
            "format": "docx",
            "report_scope": report_scope,
            "notice_count": len(notices),
            "reused_artifact": reused_artifact,
            "delivery_fingerprint": delivery_fingerprint,
            **outcomes,
        }

    @staticmethod
    def _wait_for_committed_artifact(
        repository: Repository,
        delivery_fingerprint: str,
    ) -> Path:
        for _ in range(200):
            delivery = repository.get_delivery(delivery_fingerprint)
            if delivery is None:
                break
            if delivery["status"] in {"generated", "delivered"} and delivery.get("artifact_uri"):
                report_path = REPORT_DIR / delivery["artifact_uri"]
                if report_path.is_file():
                    return report_path
            if delivery["status"] == "failed":
                raise RuntimeError(delivery.get("error") or "concurrent delivery failed")
            time.sleep(0.05)
        raise TimeoutError(f"timed out waiting for database delivery {delivery_fingerprint}")

    @staticmethod
    def source_outcomes(state: dict[str, Any]) -> dict[str, Any]:
        source_results = list(state.get("selected_sources", []))
        successful_sources = [
            {
                "source_id": item["source_id"],
                "name": item["name"],
                "record_count": item["record_count"],
                "requires_login": item["requires_login"],
            }
            for item in source_results
            if item.get("collection_status") == "success"
        ]
        failed_sources = [
            {
                "source_id": item["source_id"],
                "name": item["name"],
                "requires_login": item["requires_login"],
                "error_type": item["error_type"],
                "error": item["error"],
            }
            for item in source_results
            if item.get("collection_status") == "failed"
        ]
        return {
            "source_count": len(source_results),
            "successful_sources": successful_sources,
            "failed_sources": failed_sources,
        }

    @staticmethod
    def _publish_delivery_report(
        *,
        query: str,
        notices: list[TenderNotice],
        task_id: str,
        run_id: str,
        report_scope: str,
        delivery_fingerprint: str,
    ) -> tuple[Path, bool]:
        sample_name = build_report_filename(
            query,
            datetime.now(ZoneInfo("Asia/Shanghai")),
        )
        safe_query = sample_name.rsplit("_", maxsplit=1)[0]
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORT_DIR / f"{safe_query}_{task_id}_{delivery_fingerprint}.docx"
        Publisher._cleanup_stale_artifacts(report_path)
        if report_path.is_file():
            return report_path, True

        lock_path = report_path.with_suffix(".lock")
        try:
            lock_file = lock_path.open("xb")
        except FileExistsError:
            for _ in range(200):
                if report_path.is_file():
                    return report_path, True
                time.sleep(0.05)
            raise TimeoutError(f"timed out waiting for report delivery {delivery_fingerprint}")

        staging_dir = REPORT_DIR / ".staging" / run_id
        staged_path: Path | None = None
        lock_file.close()
        try:
            staged_path = DocxPublisher(output_dir=staging_dir).publish(
                query=query,
                notices=notices,
                report_scope=report_scope,
            )
            staged_path.replace(report_path)
        finally:
            if staged_path is not None:
                staged_path.unlink(missing_ok=True)
            lock_path.unlink(missing_ok=True)
            for directory in (staging_dir, staging_dir.parent):
                try:
                    directory.rmdir()
                except OSError:
                    pass
        return report_path, False

    @staticmethod
    def _cleanup_stale_artifacts(report_path: Path, *, stale_after_seconds: int = 300) -> None:
        now = time.time()
        lock_path = report_path.with_suffix(".lock")
        if lock_path.exists() and (
            report_path.is_file()
            or now - lock_path.stat().st_mtime > stale_after_seconds
        ):
            lock_path.unlink(missing_ok=True)

        staging_root = REPORT_DIR / ".staging"
        if not staging_root.is_dir():
            return
        for directory in staging_root.iterdir():
            try:
                is_stale = now - directory.stat().st_mtime > stale_after_seconds
            except FileNotFoundError:
                continue
            if directory.is_dir() and is_stale:
                shutil.rmtree(directory, ignore_errors=True)
        try:
            staging_root.rmdir()
        except OSError:
            pass

    @staticmethod
    def _delivery_fingerprint(
        state: dict[str, Any],
        *,
        report_scope: str,
        report_projects: list[dict[str, Any]],
    ) -> str:
        changes = list(state.get("changes", []))
        if report_scope == "full":
            delivery_type = "full_snapshot"
        elif changes and all(change["type"] == "new_project" for change in changes):
            delivery_type = "new_project"
        else:
            delivery_type = "material_change"
        payload = {
            "task_id": state["task_id"],
            "delivery_type": delivery_type,
            "projects": sorted(
                {
                    project["project_stable_fingerprint"]
                    for project in report_projects
                }
            ),
            "notices": sorted(
                {
                    document["notice"]["notice_stable_fingerprint"]
                    for project in report_projects
                    for document in project["documents"]
                }
            ),
            "changes": sorted(
                (Publisher._canonical_change(item) for item in changes),
                key=lambda item: (item["project_id"], item["type"]),
            ),
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _canonical_change(change: dict[str, Any]) -> dict[str, Any]:
        fields = change.get("fields", {})
        if isinstance(fields, list):
            canonical_fields: Any = sorted(
                [
                    {
                        "field_path": item["field_path"],
                        "previous_value": item.get("previous_value"),
                        "current_value": item.get("current_value"),
                    }
                    for item in fields
                ],
                key=lambda item: item["field_path"],
            )
        else:
            canonical_fields = fields
        return {
            "project_id": change["project_id"],
            "project_stable_fingerprint": change.get("project_stable_fingerprint"),
            "type": change["type"],
            "fields": canonical_fields,
            "notice_stable_fingerprints": sorted(
                change.get("notice_stable_fingerprints", [])
            ),
        }

    @staticmethod
    def _deduplicated_notices(projects: list[dict[str, Any]]) -> list[TenderNotice]:
        notices: list[TenderNotice] = []
        for project in projects:
            lifecycle_events: dict[str, list[TenderNotice]] = {}
            for document in project.get("documents", []):
                if not document.get("notice"):
                    continue
                notice = TenderNotice.model_validate(document["notice"])
                lifecycle_events.setdefault(notice.notice_stable_fingerprint, []).append(notice)
            for event_notices in lifecycle_events.values():
                primary = max(
                    event_notices,
                    key=lambda item: (
                        item.source.authority or 0,
                        len(item.core_content),
                        item.published_at,
                    ),
                )
                notices.append(Publisher._with_source_records(primary, event_notices))
        return notices

    @staticmethod
    def _with_source_records(
        primary: TenderNotice,
        event_notices: list[TenderNotice],
    ) -> TenderNotice:
        evidence = list(primary.evidence)
        source_facts: list[RequirementFact] = []
        existing_evidence_ids = {item.evidence_id for item in evidence}
        for index, notice in enumerate(event_notices, start=1):
            source_url = str(notice.source.source_url)
            evidence_id = f"workflow-source-{sha256(source_url.encode('utf-8')).hexdigest()[:16]}"
            if evidence_id not in existing_evidence_ids:
                evidence.append(
                    EvidenceReference(
                        evidence_id=evidence_id,
                        field_path="source.publication_records",
                        source_url=source_url,
                        locator="公告发布页面",
                        quote=notice.title,
                        fetched_at=notice.fetched_at,
                    )
                )
                existing_evidence_ids.add(evidence_id)
            source_facts.append(
                RequirementFact(
                    label=f"来源记录 {index}",
                    value=f"{notice.source.source_name}：{source_url}",
                    evidence_ids=[evidence_id],
                )
            )

        sections = list(primary.requirement_sections)
        reference_index = next(
            (index for index, section in enumerate(sections) if section.section_id == "reference"),
            None,
        )
        if reference_index is None:
            sections.append(
                RequirementSection(
                    section_id="reference",
                    title="客观参考信息",
                    summary="本公告事件的真实发布记录。",
                    facts=source_facts,
                )
            )
        else:
            reference = sections[reference_index]
            sections[reference_index] = reference.model_copy(
                update={"facts": [*reference.facts, *source_facts]}
            )
        return TenderNotice.model_validate(
            primary.model_copy(
                update={"evidence": evidence, "requirement_sections": sections}
            ).model_dump(mode="json")
        )
