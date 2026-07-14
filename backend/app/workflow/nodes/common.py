from __future__ import annotations

from typing import Any


def step(
    state: dict[str, Any],
    name: str,
    message: str,
    input_count: int | None = None,
    output_count: int | None = None,
    status: str = "completed",
) -> list[dict[str, Any]]:
    item: dict[str, Any] = {"name": name, "status": status, "message": message}
    if input_count is not None:
        item["input_count"] = input_count
    if output_count is not None:
        item["output_count"] = output_count
    return [*state.get("steps", []), item]
