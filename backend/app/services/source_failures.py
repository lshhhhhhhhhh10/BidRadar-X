from __future__ import annotations

import re
from typing import Any


def source_failure_reason(item: dict[str, Any]) -> str:
    """Return a specific, safe and user-actionable source failure reason."""

    error_type = str(item.get("error_type") or "SourceError")
    message = _safe_message(str(item.get("error") or ""))
    attempts = max(int(item.get("attempt_count") or 1), 1)
    suffix = f"（已完成 {attempts} 轮来源级尝试）"

    if "Budget" in error_type:
        return "当日预算上限已触发，本次付费请求未发送"
    if "Authentication" in error_type or "Credential" in error_type:
        return f"授权缺失或已失效：{message or error_type}"
    if "AccessBlocked" in error_type or "AccessRestricted" in error_type:
        return f"官网拒绝匿名访问或要求人工验证；系统未绕过安全校验{suffix}"
    if "Timeout" in error_type or "timed out" in message.casefold():
        return f"官网持续响应超时{suffix}"
    if "TemporaryUnavailable" in error_type or re.search(
        r"busy|rate.?limit|限流|繁忙", message, re.IGNORECASE
    ):
        return f"官网搜索服务持续繁忙或限流{suffix}"
    if "StructureChanged" in error_type or "Parse" in error_type:
        return f"官网返回结构与公开页面约定不一致：{message or error_type}"
    http_status = re.search(r"HTTP(?: status)?\s+(\d{3})", message, re.IGNORECASE)
    if http_status:
        return f"官网持续返回 HTTP {http_status.group(1)}{suffix}"
    if any(
        marker in message.casefold()
        for marker in ("network", "urlerror", "connection", "request failed", "dns")
    ):
        return f"官网网络连接持续失败：{message or error_type}{suffix}"
    return f"{error_type}：{message or '来源未返回可验证响应'}{suffix}"


def source_failure_is_retryable(error: Exception) -> bool:
    name = type(error).__name__
    message = str(error).casefold()
    if any(
        marker in name
        for marker in (
            "Timeout",
            "TemporaryUnavailable",
            "HTTPError",
        )
    ):
        return True
    return any(
        marker in message
        for marker in (
            "different event loop",
            "network",
            "request failed",
            "server busy",
            "rate limit",
            "http 5",
        )
    )


def _safe_message(message: str) -> str:
    compact = re.sub(r"\s+", " ", message).strip()
    compact = re.sub(r"https?://[^\s)]+", "官网地址", compact)
    compact = re.sub(r"(?i)\b[A-Z]:\\[^\s,;]+", "本地路径已隐藏", compact)
    compact = re.sub(
        r"(?i)\b[A-Z][A-Z0-9_]{2,}\s*=\s*[^\s,;]+",
        "配置值已隐藏",
        compact,
    )
    compact = re.sub(
        r"(?i)(token|api[_ -]?key|authorization)\s*[=:]\s*[^\s,;]+",
        lambda match: f"{match.group(1)}=***",
        compact,
    )
    return compact[:220]
