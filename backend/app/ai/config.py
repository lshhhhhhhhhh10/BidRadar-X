from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import os
from threading import RLock
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4


API_KEY_ENV = "BIDRADAR_AI_API_KEY"
SECONDARY_API_KEY_ENV = "BIDRADAR_AI_SECONDARY_API_KEY"
SECONDARY_MODEL_ENV = "BIDRADAR_AI_SECONDARY_MODEL"
PROVIDER_ENV = "BIDRADAR_AI_PROVIDER"
BASE_URL_ENV = "BIDRADAR_AI_BASE_URL"
MODEL_ENV = "BIDRADAR_AI_MODEL"
FALLBACK_MODEL_ENV = "BIDRADAR_AI_FALLBACK_MODEL"
ENABLED_ENV = "BIDRADAR_AI_ENABLED"
TIMEOUT_ENV = "BIDRADAR_AI_TIMEOUT_SECONDS"

DEFAULT_PROVIDER = "zhipu"
PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "zhipu": {
        "label": "智谱 AI",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4.7-flash",
        "fallback_model": "",
        "protocol": "chat_completions_json",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "fallback_model": "",
        "protocol": "responses_json_schema",
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "fallback_model": "",
        "protocol": "chat_completions_json",
    },
    "qwen": {
        "label": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "fallback_model": "",
        "protocol": "chat_completions_json",
    },
    "moonshot": {
        "label": "Moonshot",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "fallback_model": "",
        "protocol": "chat_completions_json",
    },
    "compatible": {
        "label": "OpenAI 兼容接口",
        "base_url": "https://example.invalid/v1",
        "model": "",
        "fallback_model": "",
        "protocol": "chat_completions_json",
    },
}

_runtime_api_key: str | None = None
_PROFILE_LOCK = RLock()
_RUNTIME_PROFILES: dict[str, "RuntimeAIProfile"] = {}


def set_runtime_api_key(value: str) -> None:
    """Compatibility setter for the single environment-style credential."""

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
    fallback_model: str | None = None
    profile_id: str = "environment"
    profile_label: str = "环境配置"

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
        base_url = _validated_base_url(os.environ.get(BASE_URL_ENV, defaults["base_url"]))
        model = os.environ.get(MODEL_ENV, defaults["model"]).strip() or defaults["model"]
        fallback_model = (
            os.environ.get(FALLBACK_MODEL_ENV, defaults.get("fallback_model", "")).strip()
            or None
        )
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
            fallback_model=fallback_model,
            profile_label=defaults["label"],
        )

    @classmethod
    def candidates(cls) -> list["AISettings"]:
        with _PROFILE_LOCK:
            runtime = [
                profile.as_settings()
                for profile in sorted(
                    _RUNTIME_PROFILES.values(),
                    key=lambda item: (item.priority, item.created_at, item.profile_id),
                )
                if profile.enabled
            ]
        environment = cls.load()
        if environment.enabled:
            runtime.append(environment)
        secondary_key = os.environ.get(SECONDARY_API_KEY_ENV, "").strip()
        if (
            secondary_key
            and _enabled_by_policy()
            and secondary_key != environment.api_key
        ):
            runtime.append(
                cls(
                    provider=environment.provider,
                    api_key=secondary_key,
                    base_url=environment.base_url,
                    model=(
                        os.environ.get(SECONDARY_MODEL_ENV, "").strip()
                        or environment.model
                    ),
                    protocol=environment.protocol,
                    timeout_seconds=environment.timeout_seconds,
                    enabled=True,
                    fallback_model=environment.fallback_model,
                    profile_id="environment-secondary",
                    profile_label=f"{environment.profile_label}备用凭据",
                )
            )
        return runtime

    def public_status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "configured": bool(self.api_key),
            "provider": self.provider,
            "model": self.model,
            "fallback_model": self.fallback_model,
            "endpoint": (
                "Chat Completions · JSON mode"
                if self.protocol == "chat_completions_json"
                else "Responses API · JSON Schema"
            ),
            "credential_storage": "backend_process_memory_or_environment",
        }


@dataclass(frozen=True)
class RuntimeAIProfile:
    profile_id: str
    label: str
    provider: str
    api_key: str = field(repr=False)
    base_url: str
    model: str
    protocol: str
    priority: int
    enabled: bool
    fallback_model: str | None
    created_at: str

    def as_settings(self) -> AISettings:
        try:
            timeout = float(os.environ.get(TIMEOUT_ENV, "35"))
        except ValueError:
            timeout = 35.0
        return AISettings(
            provider=self.provider,
            api_key=self.api_key,
            base_url=self.base_url,
            model=self.model,
            protocol=self.protocol,
            timeout_seconds=min(max(timeout, 5.0), 120.0),
            enabled=self.enabled and bool(self.api_key) and _enabled_by_policy(),
            fallback_model=self.fallback_model,
            profile_id=self.profile_id,
            profile_label=self.label,
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "label": self.label,
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "fallback_model": self.fallback_model,
            "priority": self.priority,
            "enabled": self.enabled,
            "configured": bool(self.api_key),
            "masked_key": f"••••{self.api_key[-4:]}" if len(self.api_key) >= 4 else "••••",
            "storage": "backend_process_memory",
            "created_at": self.created_at,
        }


def provider_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": provider,
            "label": values["label"],
            "default_base_url": values["base_url"],
            "default_model": values["model"],
            "protocol": values["protocol"],
        }
        for provider, values in PROVIDER_DEFAULTS.items()
    ]


def configure_runtime_profile(
    *,
    label: str,
    provider: str,
    api_key: str,
    model: str,
    base_url: str | None = None,
    fallback_model: str | None = None,
    priority: int | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    provider = provider.strip().lower()
    defaults = PROVIDER_DEFAULTS.get(provider)
    if defaults is None:
        raise ValueError("unsupported AI provider")
    clean_key = api_key.strip()
    clean_model = model.strip() or defaults["model"]
    if not 8 <= len(clean_key) <= 1024:
        raise ValueError("API Key length must be between 8 and 1024 characters")
    if not clean_model:
        raise ValueError("model is required")
    candidate_url = (base_url or defaults["base_url"]).strip()
    if provider == "compatible" and candidate_url == defaults["base_url"]:
        raise ValueError("custom compatible provider requires a base URL")
    profile_id = f"ai-{uuid4().hex[:12]}"
    with _PROFILE_LOCK:
        if len(_RUNTIME_PROFILES) >= 20:
            raise ValueError("at most 20 runtime AI profiles are allowed")
        next_priority = (
            max((item.priority for item in _RUNTIME_PROFILES.values()), default=0) + 10
            if priority is None
            else min(max(priority, 0), 10_000)
        )
        profile = RuntimeAIProfile(
            profile_id=profile_id,
            label=label.strip()[:80] or defaults["label"],
            provider=provider,
            api_key=clean_key,
            base_url=_validated_base_url(candidate_url),
            model=clean_model[:160],
            protocol=defaults["protocol"],
            priority=next_priority,
            enabled=enabled,
            fallback_model=(fallback_model or "").strip()[:160] or None,
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        _RUNTIME_PROFILES[profile_id] = profile
        return profile.public_dict()


def list_runtime_profiles() -> list[dict[str, Any]]:
    with _PROFILE_LOCK:
        return [
            profile.public_dict()
            for profile in sorted(
                _RUNTIME_PROFILES.values(),
                key=lambda item: (item.priority, item.created_at, item.profile_id),
            )
        ]


def update_runtime_profile(profile_id: str, *, enabled: bool, priority: int) -> dict[str, Any]:
    with _PROFILE_LOCK:
        current = _RUNTIME_PROFILES.get(profile_id)
        if current is None:
            raise KeyError(profile_id)
        replacement = RuntimeAIProfile(
            **{
                **current.__dict__,
                "enabled": enabled,
                "priority": min(max(priority, 0), 10_000),
            }
        )
        _RUNTIME_PROFILES[profile_id] = replacement
        return replacement.public_dict()


def remove_runtime_profile(profile_id: str) -> bool:
    with _PROFILE_LOCK:
        return _RUNTIME_PROFILES.pop(profile_id, None) is not None


def clear_runtime_profiles() -> None:
    with _PROFILE_LOCK:
        _RUNTIME_PROFILES.clear()


def aggregate_status() -> dict[str, object]:
    candidates = AISettings.candidates()
    primary = candidates[0] if candidates else AISettings.load()
    result = primary.public_status()
    runtime_profiles = list_runtime_profiles()
    result.update(
        profile_count=len(runtime_profiles),
        candidate_count=len(candidates),
        failover_enabled=len(candidates) > 1,
        active_profile_id=primary.profile_id if primary.enabled else None,
        profiles=runtime_profiles,
    )
    return result
