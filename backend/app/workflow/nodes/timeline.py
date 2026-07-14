from __future__ import annotations

from typing import Any

from .common import step


def build_timeline(state: dict[str, Any]) -> dict[str, Any]:
    projects: list[dict[str, Any]] = []
    for project in state["projects"]:
        events = [
            {
                "event_id": f"{project['project_id']}-event-{index + 1}",
                "notice_type": document["notice"]["notice_type"],
                "published_at": document["notice"]["published_at"],
                "source_id": document["notice"]["source"]["source_id"],
                "is_mirror": document["is_mirror"],
            }
            for index, document in enumerate(project["documents"])
        ]
        projects.append({**project, "events": sorted(events, key=lambda event: event["published_at"])})
    return {
        "projects": projects,
        "steps": step(state, "项目事件图谱与时序记忆", "为每个项目建立公告事件轴，并保留镜像来源。", len(projects), sum(len(p["events"]) for p in projects)),
    }
