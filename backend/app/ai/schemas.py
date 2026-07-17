from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AIContract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class IntentExtraction(AIContract):
    topic: str = Field(min_length=1, max_length=120)
    regions: list[str] = Field(default_factory=list, max_length=8)
    keywords: list[str] = Field(min_length=1, max_length=16)
    exclusions: list[str] = Field(default_factory=list, max_length=12)
    time_range_start: datetime | None = None
    time_range_end: datetime | None = None
    confidence: float = Field(ge=0, le=1)
    interpretation: str = Field(min_length=1, max_length=300)

    @field_validator("time_range_start", "time_range_end")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("AI time ranges must include a timezone")
        return value


class QueryExpansion(AIContract):
    core_terms: list[str] = Field(min_length=1, max_length=12)
    synonyms: list[str] = Field(default_factory=list, max_length=16)
    category_terms: list[str] = Field(default_factory=list, max_length=16)
    scenario_terms: list[str] = Field(default_factory=list, max_length=16)
    negative_terms: list[str] = Field(default_factory=list, max_length=12)
    search_phrases: list[str] = Field(min_length=1, max_length=12)
    expansion_summary: str = Field(min_length=1, max_length=300)


class SearchPlanDraft(AIContract):
    queries: list[str] = Field(min_length=1, max_length=8)
    recommended_source_ids: list[str] = Field(default_factory=list, max_length=6)
    strategy_summary: str = Field(min_length=1, max_length=300)


class RelevanceDecision(AIContract):
    notice_id: str = Field(min_length=1, max_length=200)
    relevant: bool
    confidence: float = Field(ge=0, le=1)
    matched_terms: list[str] = Field(default_factory=list, max_length=8)
    reason: str = Field(min_length=1, max_length=240)


class RelevanceReview(AIContract):
    decisions: list[RelevanceDecision] = Field(default_factory=list, max_length=40)


class DeduplicationDecision(AIContract):
    left_project_id: str = Field(min_length=1, max_length=200)
    right_project_id: str = Field(min_length=1, max_length=200)
    same_project: bool
    confidence: float = Field(ge=0, le=1)
    supporting_signals: list[str] = Field(default_factory=list, max_length=6)


class DeduplicationReview(AIContract):
    decisions: list[DeduplicationDecision] = Field(default_factory=list, max_length=30)


class ProjectVerification(AIContract):
    project_id: str = Field(min_length=1, max_length=200)
    supported: bool
    confidence: float = Field(ge=0, le=1)
    unsupported_claims: list[str] = Field(default_factory=list, max_length=8)
    evidence_ids: list[str] = Field(default_factory=list, max_length=12)


class FactVerification(AIContract):
    projects: list[ProjectVerification] = Field(default_factory=list, max_length=40)


class ReportFinding(AIContract):
    text: str = Field(min_length=1, max_length=400)
    evidence_ids: list[str] = Field(min_length=1, max_length=12)


class NoticeNarrative(AIContract):
    notice_id: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=800)
    risk_points: list[str] = Field(default_factory=list, max_length=8)
    next_actions: list[str] = Field(default_factory=list, max_length=8)
    evidence_ids: list[str] = Field(min_length=1, max_length=12)


class ReportDraft(AIContract):
    executive_summary: str = Field(min_length=1, max_length=1200)
    key_findings: list[ReportFinding] = Field(default_factory=list, max_length=12)
    notice_narratives: list[NoticeNarrative] = Field(default_factory=list, max_length=40)
