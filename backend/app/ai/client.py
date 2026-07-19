from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from threading import Lock
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ValidationError

from .config import AISettings
from .prompts import PromptDefinition


class AIInvocationError(RuntimeError):
    """A sanitized model-call failure safe to store in workflow audit data."""


@dataclass(frozen=True)
class AIResult:
    value: BaseModel | None
    audit: dict[str, Any]


Transport = Callable[[Request, float], dict[str, Any]]


# Free models have account-level concurrency limits.  A process-wide queue
# prevents scheduled and manual workflows from creating an avoidable burst.
_REQUEST_LOCK = Lock()
_RETRY_DELAYS_SECONDS = (1.5, 3.0, 6.0)
_RETRYABLE_PROVIDER_CODES = {"1302", "1305"}
_BALANCE_PROVIDER_CODES = {"1113"}
_PROFILE_BACKOFF_UNTIL: dict[str, float] = {}
_PROFILE_BACKOFF_SECONDS = {
    "1302": 60.0,
    "1305": 15.0,
    "network": 15.0,
}
_SAFE_PROVIDER_ERRORS = {
    "1113": "智谱账户余额不足或没有可用资源包",
    "1211": "配置的智谱模型不存在",
    "1212": "配置的智谱模型不支持当前调用方式",
    "1220": "当前智谱账户没有该模型的访问权限",
    "1302": "智谱账户触发模型速率限制",
    "1305": "智谱模型当前服务繁忙",
}


def _default_transport(request: Request, timeout: float) -> dict[str, Any]:
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _output_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    for output in response.get("output", []):
        if not isinstance(output, dict) or output.get("type") != "message":
            continue
        for content in output.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    return text
    raise AIInvocationError("model response did not contain structured output text")


def _chat_completion_text(response: dict[str, Any]) -> str:
    choices = response.get("choices", [])
    if not choices or not isinstance(choices[0], dict):
        raise AIInvocationError("chat completion did not contain a choice")
    message = choices[0].get("message", {})
    text = message.get("content") if isinstance(message, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise AIInvocationError("chat completion did not contain JSON content")
    return text


def _strict_schema(value: Any) -> Any:
    """Make Pydantic JSON Schema comply with strict structured-output rules."""

    if isinstance(value, list):
        return [_strict_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    normalized = {
        key: _strict_schema(item)
        for key, item in value.items()
        if key != "default"
    }
    properties = normalized.get("properties")
    if isinstance(properties, dict):
        normalized["required"] = list(properties)
        normalized["additionalProperties"] = False
    return normalized


class StructuredAIClient:
    def __init__(
        self,
        settings: AISettings | None = None,
        transport: Transport | None = None,
    ) -> None:
        self._explicit_settings = settings
        candidates = [settings] if settings is not None else AISettings.candidates()
        self.settings_candidates = [item for item in candidates if item is not None]
        self.settings = (
            self.settings_candidates[0]
            if self.settings_candidates
            else AISettings.load()
        )
        self.transport = transport or _default_transport

    def complete(
        self,
        prompt: PromptDefinition,
        variables: dict[str, Any],
    ) -> AIResult:
        canonical_input = json.dumps(
            variables,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        audit: dict[str, Any] = {
            "prompt_id": prompt.prompt_id,
            "prompt_version": prompt.version,
            "model": self.settings.model,
            "provider": self.settings.provider,
            "profile_id": self.settings.profile_id,
            "input_sha256": sha256(canonical_input.encode("utf-8")).hexdigest(),
            "status": "disabled" if not self.settings_candidates else "started",
        }
        if not self.settings_candidates:
            return AIResult(value=None, audit=audit)

        schema = _strict_schema(prompt.output_model.model_json_schema())
        started = time.monotonic()
        with _REQUEST_LOCK:
            ordered_candidates, deferred_profiles = _ordered_candidates(
                self.settings_candidates,
                started,
            )
            failures: list[dict[str, Any]] = []
            last_result: AIResult | None = None
            for candidate_index, settings in enumerate(ordered_candidates):
                profile_audit = {
                    **audit,
                    "model": settings.model,
                    "provider": settings.provider,
                    "profile_id": settings.profile_id,
                    "profile_label": settings.profile_label,
                }
                if deferred_profiles:
                    profile_audit["deferred_profiles"] = deferred_profiles
                result = self._complete_locked(
                    prompt,
                    canonical_input,
                    schema,
                    profile_audit,
                    started,
                    settings,
                    has_next_profile=candidate_index + 1 < len(ordered_candidates),
                )
                if result.value is not None:
                    if failures:
                        result.audit["failover_attempts"] = failures
                        result.audit["failover_count"] = len(failures)
                    return result
                failures.append(
                    {
                        "profile_id": settings.profile_id,
                        "provider": settings.provider,
                        "model": result.audit.get("model", settings.model),
                        "status": result.audit.get("status", "failed"),
                        "http_status": result.audit.get("http_status"),
                        "provider_code": result.audit.get("provider_code"),
                        "failure_reason": result.audit.get("failure_reason", "AI 调用失败"),
                    }
                )
                last_result = result
            if last_result is None:
                return AIResult(value=None, audit={**audit, "status": "disabled"})
            last_result.audit["failover_attempts"] = failures
            last_result.audit["failover_count"] = max(0, len(failures) - 1)
            return last_result

    def _complete_locked(
        self,
        prompt: PromptDefinition,
        canonical_input: str,
        schema: dict[str, Any],
        audit: dict[str, Any],
        started: float,
        settings: AISettings,
        *,
        has_next_profile: bool,
    ) -> AIResult:
        models = [settings.model]
        fallback_model = settings.fallback_model
        if fallback_model and fallback_model not in models:
            models.append(fallback_model)

        last_error: tuple[int | None, str | None, str] | None = None
        for model_index, model in enumerate(models):
            for attempt in range(len(_RETRY_DELAYS_SECONDS) + 1):
                payload = self._payload(prompt, canonical_input, schema, model, settings)
                request = Request(
                    settings.endpoint_url,
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {settings.api_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "BidRadar-X/0.1",
                    },
                    method="POST",
                )
                try:
                    response = self.transport(request, settings.timeout_seconds)
                    raw_text = (
                        _chat_completion_text(response)
                        if settings.protocol == "chat_completions_json"
                        else _output_text(response)
                    )
                    parsed = json.loads(raw_text)
                    value = prompt.output_model.model_validate(parsed)
                except HTTPError as error:
                    http_status, provider_code, safe_message = _http_error_details(error)
                    last_error = (http_status, provider_code, safe_message)
                    if provider_code in _PROFILE_BACKOFF_SECONDS:
                        _defer_profile(settings, provider_code)
                    if (
                        provider_code in _BALANCE_PROVIDER_CODES
                        and model_index + 1 < len(models)
                    ):
                        break
                    if provider_code == "1302" and has_next_profile:
                        return AIResult(
                            value=None,
                            audit=_failed_audit(
                                audit,
                                started,
                                error,
                                model=model,
                                http_status=http_status,
                                provider_code=provider_code,
                                failure_reason=safe_message,
                                attempt_count=attempt + 1,
                            ),
                        )
                    retry_limit = 1 if provider_code == "1302" else len(_RETRY_DELAYS_SECONDS)
                    if provider_code in _RETRYABLE_PROVIDER_CODES and attempt < retry_limit:
                        time.sleep(_RETRY_DELAYS_SECONDS[attempt])
                        continue
                    return AIResult(
                        value=None,
                        audit=_failed_audit(
                            audit,
                            started,
                            error,
                            model=model,
                            http_status=http_status,
                            provider_code=provider_code,
                            failure_reason=safe_message,
                            attempt_count=attempt + 1,
                        ),
                    )
                except (URLError, TimeoutError) as error:
                    _defer_profile(settings, "network")
                    if not has_next_profile and attempt < 1:
                        time.sleep(_RETRY_DELAYS_SECONDS[attempt])
                        continue
                    return AIResult(
                        value=None,
                        audit=_failed_audit(
                            audit,
                            started,
                            error,
                            model=model,
                            failure_reason="AI 服务网络超时或暂时不可达",
                            attempt_count=attempt + 1,
                        ),
                    )
                except (AIInvocationError, json.JSONDecodeError, ValidationError, ValueError, TypeError) as error:
                    audit.update(
                        status="invalid_output",
                        error_type=type(error).__name__,
                        failure_reason="AI 返回内容未通过结构化校验",
                        model=model,
                        attempt_count=attempt + 1,
                        latency_ms=round((time.monotonic() - started) * 1000),
                    )
                    return AIResult(value=None, audit=audit)

                usage = response.get("usage", {}) if isinstance(response, dict) else {}
                audit.update(
                    status="completed",
                    model=model,
                    response_id=response.get("id") or response.get("request_id"),
                    input_tokens=usage.get("input_tokens", usage.get("prompt_tokens")),
                    output_tokens=usage.get("output_tokens", usage.get("completion_tokens")),
                    attempt_count=attempt + 1,
                    latency_ms=round((time.monotonic() - started) * 1000),
                )
                _clear_profile_backoff(settings)
                if model != settings.model:
                    audit["fallback_from"] = settings.model
                return AIResult(value=value, audit=audit)

        if last_error is not None:
            http_status, provider_code, safe_message = last_error
            audit.update(
                status="failed",
                error_type="HTTPError",
                http_status=http_status,
                provider_code=provider_code,
                failure_reason=safe_message,
                latency_ms=round((time.monotonic() - started) * 1000),
            )
        return AIResult(value=None, audit=audit)
    def _payload(
        self,
        prompt: PromptDefinition,
        canonical_input: str,
        schema: dict[str, Any],
        model: str,
        settings: AISettings,
    ) -> dict[str, Any]:
        if settings.protocol == "chat_completions_json":
            payload: dict[str, Any] = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"{prompt.instructions}\n\n"
                            "必须严格返回符合以下 JSON Schema 的 JSON 对象：\n"
                            f"{json.dumps(schema, ensure_ascii=False, separators=(',', ':'))}"
                        ),
                    },
                    {"role": "user", "content": canonical_input},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": prompt.max_output_tokens,
                "stream": False,
            }
            if settings.provider == "zhipu" and "flash" in model.lower():
                payload["thinking"] = {"type": "disabled"}
            return payload
        else:
            return {
                "model": model,
                "instructions": prompt.instructions,
                "input": canonical_input,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": prompt.schema_name,
                        "strict": True,
                        "schema": schema,
                    }
                },
                "max_output_tokens": prompt.max_output_tokens,
                "store": False,
            }


def _profile_backoff_key(settings: AISettings) -> str:
    identity = "\x1f".join(
        (settings.provider, settings.base_url, settings.model, settings.api_key)
    )
    return sha256(identity.encode("utf-8")).hexdigest()


def _ordered_candidates(
    candidates: list[AISettings],
    now: float,
) -> tuple[list[AISettings], list[str]]:
    active: list[AISettings] = []
    deferred: list[tuple[float, AISettings]] = []
    for settings in candidates:
        until = _PROFILE_BACKOFF_UNTIL.get(_profile_backoff_key(settings), 0.0)
        if until > now:
            deferred.append((until, settings))
        else:
            active.append(settings)
    deferred.sort(key=lambda item: item[0])
    return (
        [*active, *(settings for _until, settings in deferred)],
        [settings.profile_id for _until, settings in deferred],
    )


def _defer_profile(settings: AISettings, reason: str) -> None:
    seconds = _PROFILE_BACKOFF_SECONDS.get(reason)
    if seconds is None:
        return
    _PROFILE_BACKOFF_UNTIL[_profile_backoff_key(settings)] = time.monotonic() + seconds


def _clear_profile_backoff(settings: AISettings) -> None:
    _PROFILE_BACKOFF_UNTIL.pop(_profile_backoff_key(settings), None)


def _http_error_details(error: HTTPError) -> tuple[int | None, str | None, str]:
    provider_code: str | None = None
    try:
        body = json.loads(error.read().decode("utf-8", "replace"))
        provider_error = body.get("error", {}) if isinstance(body, dict) else {}
        raw_code = provider_error.get("code") if isinstance(provider_error, dict) else None
        provider_code = str(raw_code) if raw_code is not None else None
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError, TypeError):
        provider_code = None
    safe_message = _SAFE_PROVIDER_ERRORS.get(
        provider_code or "",
        f"AI 服务返回 HTTP {getattr(error, 'code', '错误')}",
    )
    return getattr(error, "code", None), provider_code, safe_message


def _failed_audit(
    audit: dict[str, Any],
    started: float,
    error: Exception,
    *,
    model: str,
    failure_reason: str,
    attempt_count: int,
    http_status: int | None = None,
    provider_code: str | None = None,
) -> dict[str, Any]:
    audit.update(
        status="failed",
        error_type=type(error).__name__,
        model=model,
        failure_reason=failure_reason,
        attempt_count=attempt_count,
        latency_ms=round((time.monotonic() - started) * 1000),
    )
    if http_status is not None:
        audit["http_status"] = http_status
    if provider_code is not None:
        audit["provider_code"] = provider_code
    return audit
