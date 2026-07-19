from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, SecretStr

from ..ai import (
    AICoordinator,
    clear_runtime_api_key,
    configure_runtime_profile,
    list_runtime_profiles,
    provider_catalog,
    remove_runtime_profile,
    set_runtime_api_key,
    update_runtime_profile,
)


router = APIRouter(prefix="/api/ai", tags=["ai"])

_LOOPBACK_CLIENTS = {"127.0.0.1", "::1", "localhost", "testclient"}


class AICredentialInput(BaseModel):
    api_key: SecretStr


class AIProfileInput(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    provider: str = Field(min_length=1, max_length=40)
    api_key: SecretStr
    model: str = Field(min_length=1, max_length=160)
    base_url: str | None = Field(default=None, max_length=500)
    fallback_model: str | None = Field(default=None, max_length=160)
    priority: int | None = Field(default=None, ge=0, le=10_000)
    enabled: bool = True


class AIProfileUpdate(BaseModel):
    enabled: bool
    priority: int = Field(ge=0, le=10_000)


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


@router.get("/profiles")
def ai_profiles(request: Request) -> dict[str, object]:
    _require_loopback(request)
    return {
        "items": list_runtime_profiles(),
        "providers": provider_catalog(),
        "storage": "backend_process_memory",
    }


@router.post("/profiles", status_code=status.HTTP_201_CREATED)
def add_ai_profile(request: Request, payload: AIProfileInput) -> dict[str, object]:
    """Add a backend-only credential candidate without ever returning its secret."""

    _require_loopback(request)
    try:
        profile = configure_runtime_profile(
            label=payload.label,
            provider=payload.provider,
            api_key=payload.api_key.get_secret_value(),
            model=payload.model,
            base_url=payload.base_url,
            fallback_model=payload.fallback_model,
            priority=payload.priority,
            enabled=payload.enabled,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return {"profile": profile, "ai": AICoordinator.status()}


@router.patch("/profiles/{profile_id}")
def change_ai_profile(
    profile_id: str,
    request: Request,
    payload: AIProfileUpdate,
) -> dict[str, object]:
    _require_loopback(request)
    try:
        profile = update_runtime_profile(
            profile_id,
            enabled=payload.enabled,
            priority=payload.priority,
        )
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI 配置不存在。") from error
    return {"profile": profile, "ai": AICoordinator.status()}


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ai_profile(profile_id: str, request: Request) -> None:
    _require_loopback(request)
    if not remove_runtime_profile(profile_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI 配置不存在。")


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
