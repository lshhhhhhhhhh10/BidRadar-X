from __future__ import annotations

from typing import Any

from ...intelligence.change_detector import ChangeDetector
from ...storage.repository import Repository
from .change import _watermark_candidates
from .common import step


def update_memory(state: dict[str, Any]) -> dict[str, Any]:
    repository = Repository()
    report = dict(state["report"])
    watermarks = _watermark_candidates(state)
    if report["status"] == "generated":
        changed_ids = {change["project_id"] for change in state["changes"]}
        snapshots = [
            snapshot
            for snapshot in ChangeDetector().build_snapshots(state["projects"])
            if snapshot["project_id"] in changed_ids
        ]
        try:
            repository.commit_generated_delivery(
                task_id=state["task_id"],
                run_id=state["run_id"],
                delivery_fingerprint=report["delivery_fingerprint"],
                artifact_uri=report["filename"],
                snapshots=snapshots,
                watermarks=watermarks,
            )
        except Exception as error:
            repository.mark_delivery_failed(
                report["delivery_fingerprint"],
                state["run_id"],
                f"{type(error).__name__}: {error}",
            )
            report.update(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
            return {
                "report": report,
                "status": "failed",
                "steps": step(state, "用户反馈与长期记忆", "交付状态事务提交失败，未推进快照或水位线。", status="warning"),
            }
    elif report["status"] == "no_change":
        repository.commit_observations_and_watermarks(
            state["task_id"],
            ChangeDetector().build_snapshots(state["projects"]),
            watermarks,
        )
    return {
        "report": report,
        "steps": step(state, "用户反馈与长期记忆", "原子提交交付状态、项目快照和成功来源水位线。"),
    }
