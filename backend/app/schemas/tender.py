"""Shared data contract for tender collection, normalization, and delivery."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    JsonValue,
    field_validator,
    model_validator,
)


Sha256Fingerprint = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ContractModel(BaseModel):
    """Base settings shared by every public data-contract model."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class ScheduleSpec(ContractModel):
    """Execution cadence supplied by a monitoring task."""

    frequency: Literal["once", "daily", "weekly"] = "once"
    timezone: str = Field(default="Asia/Shanghai", min_length=1)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("timezone must be a valid IANA timezone") from error
        return value


class TaskSpec(ContractModel):
    """Normalized user intent consumed by source and workflow modules."""

    task_id: str = Field(min_length=1)
    query: str = Field(min_length=2, max_length=500)
    topic: str = Field(min_length=1)
    regions: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(min_length=1)
    exclusions: list[str] = Field(default_factory=list)
    time_range_start: AwareDatetime | None = None
    time_range_end: AwareDatetime | None = None
    schedule: ScheduleSpec = Field(default_factory=ScheduleSpec)

    @model_validator(mode="after")
    def validate_time_range(self) -> TaskSpec:
        if (
            self.time_range_start is not None
            and self.time_range_end is not None
            and self.time_range_end < self.time_range_start
        ):
            raise ValueError("time_range_end must not be earlier than time_range_start")
        return self


class SourceRecord(ContractModel):
    """One concrete publication location for a notice."""

    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_url: HttpUrl
    publication_role: Literal["original", "republication"]
    canonical_notice_url: HttpUrl | None = None
    source_notice_id: str | None = None
    authority: float | None = Field(default=None, ge=0, le=1)


class Attachment(ContractModel):
    """An attachment linked from a concrete notice publication."""

    attachment_id: str = Field(min_length=1)
    name: str | None = None
    url: HttpUrl
    media_type: str | None = None
    content_sha256: Sha256Fingerprint | None = None
    fetched_at: AwareDatetime | None = None
    archive_status: Literal["available", "failed", "unsupported"] | None = None
    archive_error: Literal[
        "source_has_no_pdf",
        "access_denied",
        "network_error",
        "unsafe_url",
        "too_large",
        "not_pdf_response",
        "write_failed",
        "unknown",
    ] | None = None
    local_path: str | None = None
    extracted_text: str | None = Field(default=None, max_length=200_000)


class EvidenceReference(ContractModel):
    """A reproducible source location supporting one structured field."""

    evidence_id: str = Field(min_length=1)
    field_path: str = Field(min_length=1)
    source_url: HttpUrl
    attachment_id: str | None = None
    document_name: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    section: str | None = None
    locator: str | None = None
    quote: str = Field(min_length=1)
    fetched_at: AwareDatetime


class RequirementFact(ContractModel):
    """A Word-ready fact that is either evidenced or explicitly unknown."""

    label: str = Field(min_length=1)
    value: str | None
    unknown_reason: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_value_provenance(self) -> RequirementFact:
        if self.value is None and not self.unknown_reason:
            raise ValueError("unknown requirement value must include unknown_reason")
        if self.value is not None and self.unknown_reason is not None:
            raise ValueError("known requirement value must not include unknown_reason")
        if self.value is not None and not self.evidence_ids:
            raise ValueError("known requirement value must include evidence_ids")
        return self


class RequirementTableRow(ContractModel):
    """One evidenced row in a Word-ready requirement table."""

    cells: list[str | None] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class RequirementTable(ContractModel):
    """A variable-width table used by technical, scoring, and similar sections."""

    title: str = Field(min_length=1)
    columns: list[str] = Field(min_length=1)
    rows: list[RequirementTableRow] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_row_widths(self) -> RequirementTable:
        expected = len(self.columns)
        if any(len(row.cells) != expected for row in self.rows):
            raise ValueError("every requirement table row must match the column count")
        return self


class RequirementSection(ContractModel):
    """One of the eight objective-content sections expected by the Word report."""

    section_id: Literal[
        "procurement",
        "qualification",
        "technical",
        "timeline",
        "commercial",
        "submission",
        "evaluation",
        "reference",
    ]
    title: str = Field(min_length=1)
    summary: str | None = None
    facts: list[RequirementFact] = Field(default_factory=list)
    tables: list[RequirementTable] = Field(default_factory=list)


class TenderNotice(ContractModel):
    """A source-specific notice linked to stable notice and project identities."""

    notice_id: str = Field(min_length=1)
    notice_type: Literal["tender", "correction", "award", "cancellation", "other"]
    opportunity_kind: Literal["prequalification", "tender", "correction"] | None = None
    project_code: str | None = None
    title: str = Field(min_length=1)
    published_at: AwareDatetime
    source: SourceRecord
    core_content: str = Field(min_length=1)
    attachments: list[Attachment] = Field(default_factory=list)
    region: str | None = None
    topic_keywords: list[str] = Field(default_factory=list)
    purchaser: str | None = None
    budget: Decimal | None = Field(default=None, ge=0)
    budget_currency: str = Field(default="CNY", pattern=r"^[A-Z]{3}$")
    deadline: AwareDatetime | None = None
    raw_content_fingerprint: Sha256Fingerprint
    notice_stable_fingerprint: Sha256Fingerprint
    project_stable_fingerprint: Sha256Fingerprint
    fetched_at: AwareDatetime
    evidence: list[EvidenceReference] = Field(default_factory=list)
    requirement_sections: list[RequirementSection] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> TenderNotice:
        attachment_ids = [attachment.attachment_id for attachment in self.attachments]
        if len(attachment_ids) != len(set(attachment_ids)):
            raise ValueError("attachment_id values must be unique within a notice")

        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_id values must be unique within a notice")

        section_ids = [section.section_id for section in self.requirement_sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("section_id values must be unique within a notice")

        evidence_paths = {item.field_path for item in self.evidence}
        structured_fields = {
            field_path
            for field_path, value in {
                "project_code": self.project_code,
                "opportunity_kind": self.opportunity_kind,
                "region": self.region,
                "topic_keywords": self.topic_keywords,
                "purchaser": self.purchaser,
                "budget": self.budget,
                "deadline": self.deadline,
            }.items()
            if value is not None and value != []
        }
        missing_field_evidence = structured_fields.difference(evidence_paths)
        if missing_field_evidence:
            raise ValueError(
                "structured fields missing evidence: "
                f"{sorted(missing_field_evidence)}"
            )

        dangling_attachments = {
            item.attachment_id
            for item in self.evidence
            if item.attachment_id is not None and item.attachment_id not in attachment_ids
        }
        if dangling_attachments:
            raise ValueError(
                f"evidence references unknown attachments: {sorted(dangling_attachments)}"
            )

        referenced_evidence = {
            evidence_id
            for section in self.requirement_sections
            for fact in section.facts
            for evidence_id in fact.evidence_ids
        }
        referenced_evidence.update(
            evidence_id
            for section in self.requirement_sections
            for table in section.tables
            for row in table.rows
            for evidence_id in row.evidence_ids
        )
        dangling_evidence = referenced_evidence.difference(evidence_ids)
        if dangling_evidence:
            raise ValueError(
                f"requirement_sections reference unknown evidence: {sorted(dangling_evidence)}"
            )
        return self


class FieldChange(ContractModel):
    """One material field change with the evidence supporting the new value."""

    field_path: str = Field(min_length=1)
    previous_value: JsonValue
    current_value: JsonValue
    evidence_ids: list[str] = Field(min_length=1)


class DeliveryRecord(ContractModel):
    """An idempotent record of a full or incremental report delivery."""

    delivery_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    delivery_type: Literal["full_snapshot", "new_project", "material_change"]
    project_stable_fingerprint: Sha256Fingerprint
    notice_stable_fingerprint: Sha256Fingerprint
    delivery_fingerprint: Sha256Fingerprint
    changes: list[FieldChange] = Field(default_factory=list)
    status: Literal["pending", "generated", "delivered", "failed"] = "pending"
    created_at: AwareDatetime
    delivered_at: AwareDatetime | None = None
    artifact_uri: str | None = None

    @model_validator(mode="after")
    def validate_delivery_state(self) -> DeliveryRecord:
        if self.delivery_type == "material_change" and not self.changes:
            raise ValueError("material_change delivery must include at least one changed field")
        if self.status == "delivered" and self.delivered_at is None:
            raise ValueError("delivered status requires delivered_at")
        return self
