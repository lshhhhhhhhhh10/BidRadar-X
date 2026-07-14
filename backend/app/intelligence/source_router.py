from __future__ import annotations

import math
from typing import Any


class SourceRouter:
    """Ranks source adapters by expected value minus acquisition cost."""

    def select(self, sources: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
        total_attempts = sum(source["attempts"] for source in sources) + 1
        ranked: list[dict[str, Any]] = []
        for source in sources:
            exploration = math.sqrt(math.log(total_attempts + 1) / (source["attempts"] + 1))
            score = (
                source["authority"] * 0.35
                + source["hit_rate"] * 0.35
                + source["stability"] * 0.20
                - source["cost"] * 0.15
                + exploration * 0.05
            )
            ranked.append({**source, "routing_score": round(score, 3)})
        return sorted(ranked, key=lambda item: item["routing_score"], reverse=True)[:limit]
