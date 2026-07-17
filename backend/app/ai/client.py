from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
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
        self.settings = settings or AISettings.load()
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
            "input_sha256": sha256(canonical_input.encode("utf-8")).hexdigest(),
            "status": "disabled" if not self.settings.enabled else "started",
        }
        if not self.settings.enabled:
            return AIResult(value=None, audit=audit)

        schema = _strict_schema(prompt.output_model.model_json_schema())
        if self.settings.protocol == "chat_completions_json":
            payload = {
                "model": self.settings.model,
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
                "max_tokens": 3200,
                "stream": False,
            }
        else:
            payload = {
                "model": self.settings.model,
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
                "max_output_tokens": 3200,
                "store": False,
            }
        request = Request(
            self.settings.endpoint_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "BidRadar-X/0.1",
            },
            method="POST",
        )
        started = time.monotonic()
        try:
            response = self.transport(request, self.settings.timeout_seconds)
            raw_text = (
                _chat_completion_text(response)
                if self.settings.protocol == "chat_completions_json"
                else _output_text(response)
            )
            parsed = json.loads(raw_text)
            value = prompt.output_model.model_validate(parsed)
        except (HTTPError, URLError, TimeoutError) as error:
            audit.update(
                status="failed",
                error_type=type(error).__name__,
                latency_ms=round((time.monotonic() - started) * 1000),
            )
            return AIResult(value=None, audit=audit)
        except (AIInvocationError, json.JSONDecodeError, ValidationError, ValueError, TypeError) as error:
            audit.update(
                status="invalid_output",
                error_type=type(error).__name__,
                latency_ms=round((time.monotonic() - started) * 1000),
            )
            return AIResult(value=None, audit=audit)

        usage = response.get("usage", {}) if isinstance(response, dict) else {}
        audit.update(
            status="completed",
            response_id=response.get("id") or response.get("request_id"),
            input_tokens=usage.get("input_tokens", usage.get("prompt_tokens")),
            output_tokens=usage.get("output_tokens", usage.get("completion_tokens")),
            latency_ms=round((time.monotonic() - started) * 1000),
        )
        return AIResult(value=value, audit=audit)
