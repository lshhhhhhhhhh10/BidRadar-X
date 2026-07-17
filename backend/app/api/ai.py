from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, SecretStr

from ..ai import AICoordinator, clear_runtime_api_key, set_runtime_api_key


router = APIRouter(prefix="/api/ai", tags=["ai"])

_LOOPBACK_CLIENTS = {"127.0.0.1", "::1", "localhost", "testclient"}


class AICredentialInput(BaseModel):
    api_key: SecretStr


def _require_loopback(request: Request) -> None:
    client_host = request.client.host if request.client is not None else ""
    if client_host not in _LOOPBACK_CLIENTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI 管理接口仅允许在后端主机本地调用。",
        )


@router.get("/status")
def ai_status() -> dict[str, object]:
    return {
        **AICoordinator.status(),
        "automatic": True,
        "fallback": "deterministic_rules",
        "stages": [
            "intent",
            "query_expansion",
            "search_plan",
            "relevance",
            "deduplication",
            "verification",
            "report",
        ],
    }


@router.put("/credential")
def set_ai_credential(request: Request, payload: AICredentialInput) -> dict[str, object]:
    """Load a key into backend memory without exposing it to the web frontend."""

    _require_loopback(request)
    api_key = payload.api_key.get_secret_value().strip()
    if not 8 <= len(api_key) <= 1024:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="API Key 长度应为 8 至 1024 个字符。",
        )
    set_runtime_api_key(api_key)
    return {**AICoordinator.status(), "storage": "backend_process_memory"}


@router.delete("/credential")
def clear_ai_credential(request: Request) -> dict[str, object]:
    _require_loopback(request)
    clear_runtime_api_key()
    return {**AICoordinator.status(), "storage": "backend_process_memory"}
