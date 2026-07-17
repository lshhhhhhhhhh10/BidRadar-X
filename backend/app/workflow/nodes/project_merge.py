from __future__ import annotations

from difflib import SequenceMatcher
from hashlib import sha256
import re
from typing import Any

from ...ai.service import AICoordinator, append_audit
from ...schemas.tender import TenderNotice
from .common import step


def _normalized(value: str | None) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", (value or "").casefold())


def _ambiguous_pairs(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(projects):
        for right in projects[left_index + 1 :]:
            similarity = SequenceMatcher(
                None, _normalized(left["title"]), _normalized(right["title"])
            ).ratio()
            same_code = bool(
                left.get("project_code")
                and left.get("project_code") == right.get("project_code")
            )
            same_purchaser = bool(
                left.get("purchaser")
                and left.get("purchaser") == right.get("purchaser")
            )
            if same_code or similarity >= 0.55 or (same_purchaser and similarity >= 0.45):
                pairs.append(
                    {
                        "left_project_id": left["project_id"],
                        "right_project_id": right["project_id"],
                        "left": {
                            "title": left["title"],
                            "project_code": left.get("project_code"),
                            "purchaser": left.get("purchaser"),
                        },
                        "right": {
                            "title": right["title"],
                            "project_code": right.get("project_code"),
                            "purchaser": right.get("purchaser"),
                        },
                        "title_similarity": round(similarity, 3),
                    }
                )
    return pairs[:30]


def _safe_merge(left: dict[str, Any], right: dict[str, Any]) -> bool:
    similarity = SequenceMatcher(
        None, _normalized(left["title"]), _normalized(right["title"])
    ).ratio()
    same_code = bool(
        left.get("project_code")
        and left.get("project_code") == right.get("project_code")
    )
    same_purchaser = bool(
        left.get("purchaser")
        and left.get("purchaser") == right.get("purchaser")
    )
    return same_code or similarity >= 0.84 or (same_purchaser and similarity >= 0.68)


def _apply_ai_merges(
    projects: list[dict[str, Any]],
    decisions: list[Any],
) -> list[dict[str, Any]]:
    by_id = {project["project_id"]: project for project in projects}
    parent = {project_id: project_id for project_id in by_id}

    def find(project_id: str) -> str:
        while parent[project_id] != project_id:
            parent[project_id] = parent[parent[project_id]]
            project_id = parent[project_id]
        return project_id

    for decision in decisions:
        left = by_id.get(decision.left_project_id)
        right = by_id.get(decision.right_project_id)
        if (
            left is None
            or right is None
            or not decision.same_project
            or decision.confidence < 0.90
            or not _safe_merge(left, right)
        ):
            continue
        left_root = find(left["project_id"])
        right_root = find(right["project_id"])
        if left_root != right_root:
            parent[right_root] = left_root

    groups: dict[str, list[dict[str, Any]]] = {}
    for project in projects:
        groups.setdefault(find(project["project_id"]), []).append(project)

    merged: list[dict[str, Any]] = []
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
            continue
        fingerprints = sorted(item["project_stable_fingerprint"] for item in group)
        fingerprint = sha256("|".join(fingerprints).encode("utf-8")).hexdigest()
        documents = [document for item in group for document in item["documents"]]
        seen_notices: set[str] = set()
        mirror_count = 0
        updated_documents = []
        for document in documents:
            notice_fingerprint = document["notice"]["notice_stable_fingerprint"]
            is_mirror = notice_fingerprint in seen_notices
            seen_notices.add(notice_fingerprint)
            mirror_count += int(is_mirror)
            updated_documents.append({**document, "is_mirror": is_mirror})
        primary = max(group, key=lambda item: len(item["documents"]))
        merged.append(
            {
                **primary,
                "project_id": f"project-{fingerprint[:16]}",
                "project_stable_fingerprint": fingerprint,
                "project_code": next(
                    (item.get("project_code") for item in group if item.get("project_code")),
                    None,
                ),
                "purchaser": next(
                    (item.get("purchaser") for item in group if item.get("purchaser")),
                    None,
                ),
                "documents": updated_documents,
                "mirror_count": mirror_count,
            }
        )
    return merged


def merge_projects(state: dict[str, Any]) -> dict[str, Any]:
    projects_by_fingerprint: dict[str, dict[str, Any]] = {}
    seen_notice_fingerprints: dict[str, set[str]] = {}
    for payload in state["relevant_documents"]:
        notice = TenderNotice.model_validate(payload)
        project_fingerprint = notice.project_stable_fingerprint
        project = projects_by_fingerprint.get(project_fingerprint)
        if project is None:
            project = {
                "project_id": f"project-{project_fingerprint[:16]}",
                "project_stable_fingerprint": project_fingerprint,
                "project_code": notice.project_code,
                "title": notice.title,
                "purchaser": notice.purchaser,
                "documents": [],
                "mirror_count": 0,
            }
            projects_by_fingerprint[project_fingerprint] = project
            seen_notice_fingerprints[project_fingerprint] = set()

        is_mirror = notice.notice_stable_fingerprint in seen_notice_fingerprints[project_fingerprint]
        if is_mirror:
            project["mirror_count"] += 1
        seen_notice_fingerprints[project_fingerprint].add(notice.notice_stable_fingerprint)
        project["documents"].append(
            {
                "notice": notice.model_dump(mode="json"),
                "is_mirror": is_mirror,
            }
        )

    projects = list(projects_by_fingerprint.values())
    candidate_pairs = _ambiguous_pairs(projects)
    audit = None
    ai_merge_count = 0
    if candidate_pairs:
        coordinator = AICoordinator()
        review, audit = coordinator.review_duplicates({"candidate_pairs": candidate_pairs})
        if review is not None:
            before = len(projects)
            projects = _apply_ai_merges(projects, review.decisions)
            ai_merge_count = before - len(projects)
    mirror_count = sum(project["mirror_count"] for project in projects)
    funnel = {**state["funnel"], "projects": len(projects), "mirrors": mirror_count}
    return {
        "projects": projects,
        "funnel": funnel,
        **({"ai_audit": append_audit(state, audit)} if audit is not None else {}),
        "steps": step(
            state,
            "项目实体归并与跨站去重",
            f"按稳定指纹和保守的 AI 歧义复核形成 {len(projects)} 个项目，AI 合并 {ai_merge_count} 组，识别 {mirror_count} 条同公告镜像。",
            len(state["relevant_documents"]),
            len(projects),
        ),
    }
