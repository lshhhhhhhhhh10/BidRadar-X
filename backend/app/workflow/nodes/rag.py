from __future__ import annotations

from typing import Any

from ...intelligence.evidence_rag import EvidenceRAG
from .common import step


def analyze_with_rag(state: dict[str, Any]) -> dict[str, Any]:
    projected_projects = []
    for project in state["projects"]:
        projected_documents = [
            {
                "content": "\n\n".join(
                    [
                        document["notice"]["core_content"],
                        *[
                            attachment.get("extracted_text") or ""
                            for attachment in document["notice"].get("attachments", [])
                            if attachment.get("extracted_text")
                        ],
                    ]
                )[:240_000],
                "budget": document["notice"]["budget"],
                "deadline": document["notice"]["deadline"],
                "purchaser": document["notice"]["purchaser"],
            }
            for document in project["documents"]
        ]
        projected_projects.append({**project, "documents": projected_documents})
    analysis = EvidenceRAG().analyze(state["query"], projected_projects, state["evidence"])
    return {
        "analysis": analysis,
        "steps": step(state, "Agentic Evidence RAG", "混合召回并为结构化事实绑定证据编号。", len(state["evidence"]), len(analysis)),
    }
