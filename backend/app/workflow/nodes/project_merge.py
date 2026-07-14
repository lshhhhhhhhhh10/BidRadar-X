from __future__ import annotations

from typing import Any

from ...schemas.tender import TenderNotice
from .common import step


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
    mirror_count = sum(project["mirror_count"] for project in projects)
    funnel = {**state["funnel"], "projects": len(projects), "mirrors": mirror_count}
    return {
        "projects": projects,
        "funnel": funnel,
        "steps": step(
            state,
            "项目实体归并与跨站去重",
            f"按项目稳定指纹形成 {len(projects)} 个项目，识别 {mirror_count} 条同公告镜像。",
            len(state["relevant_documents"]),
            len(projects),
        ),
    }
