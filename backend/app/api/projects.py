from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..storage.repository import Repository


router = APIRouter(prefix="/api", tags=["projects"])

def build_source_project_profiles(state: dict) -> list[dict]:
    return [
        _build_project_profile(state["run_id"], project)
        for project in state.get("projects", [])
    ]


def build_source_project_summaries(state: dict) -> list[dict]:
    """Build the lightweight list view; requirement modules are loaded on click."""

    summaries: list[dict] = []
    for project in state.get("projects", []):
        profile = _build_project_profile(state["run_id"], project)
        summaries.append({**profile, "details_loaded": False, "modules": []})
    return summaries


def _build_project_profile(run_id: str, project: dict) -> dict:
    notices = [
        document["notice"]
        for document in project.get("documents", [])
        if isinstance(document.get("notice"), dict)
    ]
    primary = max(
        notices,
        key=lambda notice: (
            notice.get("source", {}).get("authority") or 0,
            notice.get("published_at") or "",
            len(notice.get("core_content") or ""),
        ),
    )
    evidence = {
        item["evidence_id"]: item
        for notice in notices
        for item in notice.get("evidence", [])
    }
    modules = [
        _build_requirement_module(section, evidence)
        for section in primary.get("requirement_sections", [])
    ]
    source = primary.get("source", {})
    return {
        "run_id": run_id,
        "project_id": project["project_id"],
        "project_code": project.get("project_code"),
        "title": primary.get("title") or project.get("title") or "未命名项目",
        "purchaser": primary.get("purchaser") or "采购人未披露",
        "published_at": primary.get("published_at") or "",
        "url": source.get("source_url") or "",
        "source_name": source.get("source_name") or "",
        "budget": primary.get("budget"),
        "deadline": primary.get("deadline"),
        "summary": primary.get("core_content") or "公告未提供正文摘要",
        "evidence_count": len(evidence),
        "details_loaded": True,
        "modules": modules,
    }


def _build_requirement_module(section: dict, evidence: dict[str, dict]) -> dict:
    return {
        "id": section["section_id"],
        "title": section["title"],
        "summary": section.get("summary") or "",
        "facts": [
            {
                "label": fact["label"],
                "value": (
                    str(fact["value"])
                    if fact.get("value") is not None
                    else f"未知（{fact.get('unknown_reason') or '来源未披露'}）"
                ),
                "source": _evidence_locations(fact.get("evidence_ids", []), evidence),
            }
            for fact in section.get("facts", [])
        ],
        "tables": [
            {
                "title": table["title"],
                "columns": table["columns"],
                "rows": [row["cells"] for row in table.get("rows", [])],
            }
            for table in section.get("tables", [])
        ],
    }


def _evidence_locations(evidence_ids: list[str], evidence: dict[str, dict]) -> str:
    locations: list[str] = []
    for evidence_id in evidence_ids:
        item = evidence.get(evidence_id)
        if item is None:
            continue
        location = item.get("document_name") or item.get("source_url") or "来源页面"
        if item.get("page_number") is not None:
            location = f"{location} 第 {item['page_number']} 页"
        elif item.get("locator"):
            location = f"{location} · {item['locator']}"
        locations.append(location)
    return "；".join(locations) if locations else "来源未提供字段级定位"


@router.get("/runs/{run_id}/projects")
def list_projects(run_id: str) -> dict[str, list[dict]]:
    repository = Repository()
    if repository.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"items": repository.list_project_profiles(run_id)}


@router.get("/runs/{run_id}/projects/{project_id}")
def get_project(run_id: str, project_id: str) -> dict:
    repository = Repository()
    profile = repository.get_project_profile(run_id, project_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="未找到该项目或任务运行记录")
    if profile.get("details_loaded") is False:
        run = repository.get_run(run_id)
        source_project = next(
            (
                item
                for item in (run or {}).get("projects", [])
                if item.get("project_id") == project_id
            ),
            None,
        )
        if source_project is None:
            raise HTTPException(status_code=404, detail="未找到该项目的来源记录")
        profile = _build_project_profile(run_id, source_project)
        repository.save_project_profiles(run_id, [profile])
    return profile


@router.get("/runs/{run_id}/projects/{project_id}/modules/{module_id}")
def get_project_module(run_id: str, project_id: str, module_id: str) -> dict:
    profile = get_project(run_id, project_id)
    module = next((item for item in profile["modules"] if item["id"] == module_id), None)
    if module is None:
        raise HTTPException(status_code=404, detail="未找到该要求模块")
    return {
        "run_id": run_id,
        "project_id": project_id,
        "project_title": profile["title"],
        "project_code": profile.get("project_code"),
        "module": module,
    }
