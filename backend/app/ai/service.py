from __future__ import annotations

from typing import Any, TypeVar, cast

from pydantic import BaseModel

from .client import AIResult, StructuredAIClient
from .config import aggregate_status
from .prompts import (
    DEDUP_PROMPT,
    INTENT_PROMPT,
    QUERY_EXPANSION_PROMPT,
    RELEVANCE_PROMPT,
    REPORT_PROMPT,
    SEARCH_PLAN_PROMPT,
    VERIFY_PROMPT,
    PromptDefinition,
)
from .schemas import (
    DeduplicationReview,
    FactVerification,
    IntentExtraction,
    QueryExpansion,
    RelevanceReview,
    ReportDraft,
    SearchPlanDraft,
)


ResultModel = TypeVar("ResultModel", bound=BaseModel)


class AICoordinator:
    """One policy boundary for all optional model calls in the workflow."""

    def __init__(self, client: StructuredAIClient | None = None) -> None:
        self.client = client or StructuredAIClient()

    @property
    def enabled(self) -> bool:
        return bool(self.client.settings_candidates)

    @staticmethod
    def status() -> dict[str, object]:
        return aggregate_status()

    def _run(
        self,
        prompt: PromptDefinition,
        variables: dict[str, Any],
        output_type: type[ResultModel],
    ) -> tuple[ResultModel | None, dict[str, Any]]:
        result: AIResult = self.client.complete(prompt, variables)
        value = result.value
        return (
            cast(ResultModel, value) if isinstance(value, output_type) else None,
            result.audit,
        )

    def understand_intent(self, variables: dict[str, Any]) -> tuple[IntentExtraction | None, dict[str, Any]]:
        return self._run(INTENT_PROMPT, variables, IntentExtraction)

    def plan_search(self, variables: dict[str, Any]) -> tuple[SearchPlanDraft | None, dict[str, Any]]:
        return self._run(SEARCH_PLAN_PROMPT, variables, SearchPlanDraft)

    def expand_query(self, variables: dict[str, Any]) -> tuple[QueryExpansion | None, dict[str, Any]]:
        return self._run(QUERY_EXPANSION_PROMPT, variables, QueryExpansion)

    def review_relevance(self, variables: dict[str, Any]) -> tuple[RelevanceReview | None, dict[str, Any]]:
        return self._run(RELEVANCE_PROMPT, variables, RelevanceReview)

    def review_duplicates(self, variables: dict[str, Any]) -> tuple[DeduplicationReview | None, dict[str, Any]]:
        return self._run(DEDUP_PROMPT, variables, DeduplicationReview)

    def verify_facts(self, variables: dict[str, Any]) -> tuple[FactVerification | None, dict[str, Any]]:
        return self._run(VERIFY_PROMPT, variables, FactVerification)

    def draft_report(self, variables: dict[str, Any]) -> tuple[ReportDraft | None, dict[str, Any]]:
        return self._run(REPORT_PROMPT, variables, ReportDraft)


def append_audit(state: dict[str, Any], audit: dict[str, Any]) -> list[dict[str, Any]]:
    return [*state.get("ai_audit", []), audit]
