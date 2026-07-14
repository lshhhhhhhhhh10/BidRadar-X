from __future__ import annotations

from typing import Any, Protocol


class SourceAdapter(Protocol):
    metadata: dict[str, Any]

    async def collect(self, task_spec: dict[str, Any], search_plan: dict[str, Any]) -> list[dict[str, Any]]:
        ...
