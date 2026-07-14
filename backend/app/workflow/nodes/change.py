from __future__ import annotations

from typing import Any

from ...intelligence.change_detector import ChangeDetector
from ...storage.repository import Repository
from .common import step


def detect_changes(state: dict[str, Any]) -> dict[str, Any]:
    repository = Repository()
    previous = repository.load_project_snapshots(state["task_id"])
    detector = ChangeDetector()
    snapshots = detector.build_snapshots(state["projects"])
    changes = detector.compare(snapshots, previous)
    return {
        "changes": changes,
        "steps": step(state, "字段级时序变化检测", "对比项目快照，只保留新项目和实质变化。", len(state["analysis"]), len(changes)),
    }


def _watermark_candidates(state: dict[str, Any]) -> list[dict[str, Any]]:
    documents_by_source: dict[str, list[dict[str, Any]]] = {}
    for notice in state.get("raw_documents", []):
        source_id = notice["source"]["source_id"]
        documents_by_source.setdefault(source_id, []).append(notice)

    candidates: list[dict[str, Any]] = []
    for source in state.get("selected_sources", []):
        if source.get("collection_status") != "success":
            continue
        notices = documents_by_source.get(source["source_id"], [])
        candidates.append(
            {
                "task_id": state["task_id"],
                "source_id": source["source_id"],
                "run_id": state["run_id"],
                "record_count": source.get("record_count", len(notices)),
                "processed_through": state.get("task_spec", {}).get("time_range_end"),
                "max_published_at": max(
                    (notice["published_at"] for notice in notices),
                    default=None,
                ),
                "max_fetched_at": max(
                    (notice["fetched_at"] for notice in notices),
                    default=None,
                ),
                "notice_stable_fingerprints": sorted(
                    {notice["notice_stable_fingerprint"] for notice in notices}
                ),
            }
        )
    return candidates
