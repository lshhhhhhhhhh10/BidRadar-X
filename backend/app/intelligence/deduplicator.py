from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


def _normalized(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", value.lower())


class ProjectDeduplicator:
    """Separates cross-site mirrors from distinct project lifecycle events."""

    def merge(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        for document in documents:
            project = self._find_project(projects, document)
            if project is None:
                project = {
                    "project_id": f"project-{len(projects) + 1:03d}",
                    "project_code": document.get("project_code"),
                    "title": document["title"],
                    "purchaser": document.get("purchaser"),
                    "documents": [],
                    "mirror_count": 0,
                }
                projects.append(project)

            is_mirror = any(self._is_mirror(existing, document) for existing in project["documents"])
            if is_mirror:
                project["mirror_count"] += 1
            project["documents"].append({**document, "is_mirror": is_mirror})
        return projects

    def _find_project(self, projects: list[dict[str, Any]], document: dict[str, Any]) -> dict[str, Any] | None:
        for project in projects:
            if document.get("project_code") and document.get("project_code") == project.get("project_code"):
                return project
            title_score = SequenceMatcher(None, _normalized(document["title"]), _normalized(project["title"])).ratio()
            same_purchaser = document.get("purchaser") == project.get("purchaser")
            if title_score >= 0.78 and same_purchaser:
                return project
        return None

    def _is_mirror(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        if left.get("notice_type") != right.get("notice_type"):
            return False
        similarity = SequenceMatcher(None, _normalized(left["content"]), _normalized(right["content"])).ratio()
        return similarity >= 0.82
