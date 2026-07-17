from __future__ import annotations

from dataclasses import dataclass, field
import os
from urllib.parse import urlparse


API_KEY_ENV = "BIDRADAR_AI_API_KEY"
PROVIDER_ENV = "BIDRADAR_AI_PROVIDER"
BASE_URL_ENV = "BIDRADAR_AI_BASE_URL"
MODEL_ENV = "BIDRADAR_AI_MODEL"
ENABLED_ENV = "BIDRADAR_AI_ENABLED"
TIMEOUT_ENV = "BIDRADAR_AI_TIMEOUT_SECONDS"

DEFAULT_PROVIDER = "zhipu"
PROVIDER_DEFAULTS = {
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-5.2",
        "protocol": "chat_completions_json",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.6-luna",
        "protocol": "responses_json_schema",
    },
}

_runtime_api_key: str | None = None


def set_runtime_api_key(value: str) -> None:
    """Keep a locally supplied key in this backend process only."""

    global _runtime_api_key
    _runtime_api_key = value.strip()


def clear_runtime_api_key() -> None:
    global _runtime_api_key
    _runtime_api_key = None


def _api_key() -> str:
    return (_runtime_api_key or os.environ.get(API_KEY_ENV, "")).strip()


def _enabled_by_policy() -> bool:
    return os.environ.get(ENABLED_ENV, "auto").strip().lower() not in {
        "0",
        "false",
        "off",
        "disabled",
    }


def _validated_base_url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlparse(candidate)
    is_loopback_http = parsed.scheme == "http" and parsed.hostname in {
        "127.0.0.1",
        "localhost",
        "::1",
    }
    if parsed.scheme != "https" and not is_loopback_http:
        raise ValueError("AI base URL must use HTTPS unless it is a loopback service")
    if not parsed.netloc:
        raise ValueError("AI base URL must include a host")
    return candidate


@dataclass(frozen=True)
class AISettings:
    provider: str
    api_key: str = field(repr=False)
    base_url: str
    model: str
    protocol: str
    timeout_seconds: float
    enabled: bool

    @property
    def endpoint_url(self) -> str:
        path = "chat/completions" if self.protocol == "chat_completions_json" else "responses"
        return f"{self.base_url}/{path}"

    @classmethod
    def load(cls) -> "AISettings":
        api_key = _api_key()
        provider = os.environ.get(PROVIDER_ENV, DEFAULT_PROVIDER).strip().lower()
        defaults = PROVIDER_DEFAULTS.get(provider)
        if defaults is None:
            raise ValueError(f"unsupported AI provider: {provider}")
        base_url = _validated_base_url(
            os.environ.get(BASE_URL_ENV, defaults["base_url"])
        )
        model = os.environ.get(MODEL_ENV, defaults["model"]).strip() or defaults["model"]
        try:
            timeout = float(os.environ.get(TIMEOUT_ENV, "35"))
        except ValueError:
            timeout = 35.0
        timeout = min(max(timeout, 5.0), 120.0)
        return cls(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            protocol=defaults["protocol"],
            timeout_seconds=timeout,
            enabled=bool(api_key) and _enabled_by_policy(),
        )

    def public_status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "configured": bool(self.api_key),
            "provider": self.provider,
            "model": self.model,
            "endpoint": (
                "Chat Completions · JSON mode"
                if self.protocol == "chat_completions_json"
                else "Responses API · JSON Schema"
            ),
            "credential_storage": "backend_process_memory_or_environment",
        }
