from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


def _tokens(text: str) -> set[str]:
    text = re.sub(r"\s+", "", text.lower())
    chinese_bigrams = {text[index : index + 2] for index in range(max(0, len(text) - 1))}
    latin = set(re.findall(r"[a-z0-9]+", text))
    return chinese_bigrams | latin


class EvidenceRAG:
    """Small local hybrid retriever that keeps every conclusion tied to evidence."""

    def analyze(
        self,
        query: str,
        projects: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        query_tokens = _tokens(query)
        analyses: list[dict[str, Any]] = []
        for project in projects:
            candidates = [item for item in evidence if item["project_id"] == project["project_id"]]
            lexical_rank = sorted(
                candidates,
                key=lambda item: len(query_tokens & _tokens(item["content"])),
                reverse=True,
            )
            semantic_rank = sorted(
                candidates,
                key=lambda item: SequenceMatcher(None, query, item["content"][:200]).ratio(),
                reverse=True,
            )
            fused: dict[str, float] = {}
            for rank, item in enumerate(lexical_rank, start=1):
                fused[item["evidence_id"]] = fused.get(item["evidence_id"], 0.0) + 1 / (60 + rank)
            for rank, item in enumerate(semantic_rank, start=1):
                fused[item["evidence_id"]] = fused.get(item["evidence_id"], 0.0) + 1 / (60 + rank)
            selected = sorted(candidates, key=lambda item: fused.get(item["evidence_id"], 0), reverse=True)[:3]
            primary = project["documents"][0]
            analyses.append(
                {
                    "project_id": project["project_id"],
                    "summary": primary["content"][:140],
                    "facts": {
                        "budget": primary.get("budget"),
                        "deadline": primary.get("deadline"),
                        "purchaser": primary.get("purchaser"),
                    },
                    "evidence_ids": [item["evidence_id"] for item in selected],
                    "retrieval_method": "lexical + semantic + RRF",
                }
            )
        return analyses
