from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..storage.repository import Repository


router = APIRouter(prefix="/api", tags=["projects"])


@router.get("/runs/{run_id}/projects")
def list_projects(run_id: str) -> dict[str, list[dict]]:
    return {"items": Repository().list_project_profiles(run_id)}


@router.get("/runs/{run_id}/projects/{project_id}")
def get_project(run_id: str, project_id: str) -> dict:
    profile = Repository().get_project_profile(run_id, project_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="未找到该项目或任务运行记录")
    return profile


@router.get("/runs/{run_id}/projects/{project_id}/modules/{module_id}")
def get_project_module(run_id: str, project_id: str, module_id: str) -> dict:
    profile = Repository().get_project_profile(run_id, project_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="未找到该项目或任务运行记录")
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
