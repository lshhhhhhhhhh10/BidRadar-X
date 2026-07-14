from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
import unicodedata
from typing import Any

from ..schemas.tender import TenderNotice


class ChangeDetector:
    """Builds stable project snapshots and compares only material business facts."""

    tracked_fields = ("budget", "deadline", "purchaser")

    def build_snapshots(self, projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self._build_project_snapshot(project) for project in projects]

    def compare(
        self,
        current: list[dict[str, Any]],
        previous: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []
        for snapshot in current:
            project_fingerprint = snapshot["project_stable_fingerprint"]
            before = previous.get(project_fingerprint) or previous.get(snapshot["project_id"])
            if before is None:
                changes.append(
                    {
                        "project_id": snapshot["project_id"],
                        "project_stable_fingerprint": project_fingerprint,
                        "type": "new_project",
                        "fields": snapshot["facts"],
                        "notice_stable_fingerprints": [
                            item["notice_stable_fingerprint"] for item in snapshot["lifecycle"]
                        ],
                    }
                )
                continue

            before_facts = before.get("facts", before)
            before_normalized = before.get("normalized_facts") or {
                field: self._normalize(field, before_facts.get(field))
                for field in self.tracked_fields
            }
            field_changes: list[dict[str, Any]] = []
            for field in self.tracked_fields:
                if before_normalized.get(field) == snapshot["normalized_facts"].get(field):
                    continue
                evidence = self._field_evidence(snapshot, field)
                field_changes.append(
                    {
                        "field_path": field,
                        "previous_value": before_facts.get(field),
                        "current_value": snapshot["facts"].get(field),
                        "evidence_ids": [item["evidence_id"] for item in evidence],
                        "evidence": evidence,
                    }
                )

            before_lifecycle = sorted(
                before.get("lifecycle", []),
                key=lambda item: (item["notice_stable_fingerprint"], item["notice_type"]),
            )
            if before_lifecycle != snapshot["lifecycle"]:
                lifecycle_evidence = self._lifecycle_evidence(snapshot)
                field_changes.append(
                    {
                        "field_path": "notice_lifecycle",
                        "previous_value": before_lifecycle,
                        "current_value": snapshot["lifecycle"],
                        "evidence_ids": [item["evidence_id"] for item in lifecycle_evidence],
                        "evidence": lifecycle_evidence,
                    }
                )

            if field_changes:
                changes.append(
                    {
                        "project_id": snapshot["project_id"],
                        "project_stable_fingerprint": project_fingerprint,
                        "type": "material_change",
                        "fields": field_changes,
                        "notice_stable_fingerprints": [
                            item["notice_stable_fingerprint"] for item in snapshot["lifecycle"]
                        ],
                    }
                )
        return changes

    def _build_project_snapshot(self, project: dict[str, Any]) -> dict[str, Any]:
        notices = [
            TenderNotice.model_validate(document["notice"])
            for document in project.get("documents", [])
            if document.get("notice")
        ]
        if not notices:
            raise ValueError(f"project {project['project_id']} has no contract notice")
        primary = max(
            notices,
            key=lambda item: (
                item.published_at,
                item.source.authority or 0,
                len(item.core_content),
            ),
        )
        facts = {
            "budget": str(primary.budget) if primary.budget is not None else None,
            "deadline": primary.deadline.isoformat() if primary.deadline is not None else None,
            "purchaser": primary.purchaser,
        }
        lifecycle = sorted(
            {
                (notice.notice_stable_fingerprint, notice.notice_type)
                for notice in notices
            }
        )
        lifecycle_payload = [
            {"notice_stable_fingerprint": fingerprint, "notice_type": notice_type}
            for fingerprint, notice_type in lifecycle
        ]
        normalized_facts = {
            field: self._normalize(field, value) for field, value in facts.items()
        }
        fingerprint_payload = {
            "normalized_facts": normalized_facts,
            "lifecycle": lifecycle_payload,
        }
        canonical = json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "project_id": project["project_id"],
            "project_stable_fingerprint": project["project_stable_fingerprint"],
            "snapshot_fingerprint": sha256(canonical.encode("utf-8")).hexdigest(),
            "facts": facts,
            "normalized_facts": normalized_facts,
            "lifecycle": lifecycle_payload,
            "notices": [
                notice.model_dump(mode="json")
                for notice in sorted(
                    notices,
                    key=lambda item: (
                        item.notice_stable_fingerprint,
                        item.source.source_id,
                        str(item.source.source_url),
                    ),
                )
            ],
        }

    @staticmethod
    def _normalize(field: str, value: Any) -> Any:
        if value is None:
            return None
        if field == "budget":
            try:
                normalized = Decimal(str(value)).normalize()
            except InvalidOperation:
                return str(value).strip()
            return format(normalized, "f")
        if field == "deadline":
            try:
                return datetime.fromisoformat(str(value)).isoformat(timespec="seconds")
            except ValueError:
                return str(value).strip()
        text = unicodedata.normalize("NFKC", str(value))
        return re.sub(r"\s+", "", text).casefold()

    @staticmethod
    def _field_evidence(snapshot: dict[str, Any], field: str) -> list[dict[str, Any]]:
        evidence = [
            item
            for notice in snapshot["notices"]
            for item in notice.get("evidence", [])
            if item["field_path"] == field
        ]
        return evidence

    @staticmethod
    def _lifecycle_evidence(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for notice in snapshot["notices"]:
            source_url = notice["source"]["source_url"]
            evidence_id = f"lifecycle-{notice['notice_stable_fingerprint'][:16]}"
            evidence.append(
                {
                    "evidence_id": evidence_id,
                    "field_path": "notice_lifecycle",
                    "source_url": source_url,
                    "quote": notice["title"],
                    "fetched_at": notice["fetched_at"],
                }
            )
        return evidence
