from __future__ import annotations

from pathlib import Path
import platform
import subprocess

from fastapi import APIRouter, HTTPException, Request, status

from ..services.attachment_archive import ATTACHMENT_DIR
from ..storage.repository import Repository


router = APIRouter(prefix="/api", tags=["attachments"])
_LOOPBACK_CLIENTS = {"127.0.0.1", "::1", "localhost", "testclient"}


@router.post(
    "/runs/{run_id}/projects/{project_id}/attachments/{attachment_id}/reveal"
)
def reveal_local_attachment(
    run_id: str,
    project_id: str,
    attachment_id: str,
    request: Request,
) -> dict[str, object]:
    _require_loopback(request)
    run = Repository().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="未找到对应检索记录。")
    attachment = _find_attachment(run, project_id, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="未找到对应招标文件。")
    local_path = attachment.get("local_path")
    if not isinstance(local_path, str) or not local_path:
        raise HTTPException(status_code=409, detail="该招标文件尚未保存到本机。")
    path = Path(local_path).expanduser().resolve()
    root = ATTACHMENT_DIR.expanduser().resolve()
    if not path.is_relative_to(root):
        raise HTTPException(status_code=403, detail="招标文件路径不在本地归档目录中。")
    if not path.is_file() or path.suffix.casefold() != ".pdf":
        raise HTTPException(status_code=410, detail="本地招标文件已移动或缺失。")
    try:
        _reveal_in_file_manager(path)
    except (OSError, subprocess.SubprocessError) as error:
        raise HTTPException(
            status_code=500,
            detail="无法打开本机文件管理器，请检查系统权限。",
        ) from error
    return {
        "revealed": True,
        "filename": path.name,
        "folder": root.name,
    }


def _require_loopback(request: Request) -> None:
    client_host = request.client.host if request.client is not None else ""
    if client_host not in _LOOPBACK_CLIENTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="本地文件管理接口仅允许在本机调用。",
        )


def _find_attachment(run: dict, project_id: str, attachment_id: str) -> dict | None:
    for project in run.get("projects", []):
        if project.get("project_id") != project_id:
            continue
        for document in project.get("documents", []):
            notice = document.get("notice", {})
            for attachment in notice.get("attachments", []):
                if attachment.get("attachment_id") == attachment_id:
                    return attachment
    return None


def _reveal_in_file_manager(path: Path) -> None:
    system = platform.system()
    if system == "Darwin":
        command = ["open", "-R", str(path)]
    elif system == "Windows":
        command = ["explorer", f"/select,{path}"]
    else:
        command = ["xdg-open", str(path.parent)]
    subprocess.run(
        command,
        check=True,
        timeout=8,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


__all__ = ["router"]
