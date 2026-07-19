from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any

from ..schemas.tender import TenderNotice


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(re.findall(r"[\w\u3400-\u9fff]+", text))


def _is_contained(needle: Any, haystack: str) -> bool:
    normalized_needle = _normalized(needle)
    if not normalized_needle:
        return False
    return normalized_needle in _normalized(haystack)


@dataclass(frozen=True)
class FactConsistencyResult:
    passed: bool
    checked_claims: int
    supported_claims: int
    unsupported_claims: tuple[str, ...]
    project_results: tuple[dict[str, Any], ...]

    @property
    def support_rate(self) -> float:
        if self.checked_claims == 0:
            return 0.0
        return round(self.supported_claims / self.checked_claims, 4)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checked_claims": self.checked_claims,
            "supported_claims": self.supported_claims,
            "support_rate": self.support_rate,
            "unsupported_claims": list(self.unsupported_claims),
            "project_results": list(self.project_results),
            "method": "deterministic_evidence_binding_v1",
            "scope": (
                "验证证据 ID、项目归属、原文引文和结构化字段；"
                "该闸门不替代人工标注的语义一致率评估。"
            ),
        }


class FactConsistencyValidator:
    """Reject generated claims that cannot be traced to collected source text."""

    def validate(self, state: dict[str, Any]) -> FactConsistencyResult:
        project_notices: dict[str, list[TenderNotice]] = {}
        project_texts: dict[str, str] = {}
        unsupported: list[str] = []
        project_results: list[dict[str, Any]] = []
        checked = 0
        supported = 0

        for project in state.get("projects", []):
            project_id = str(project.get("project_id", ""))
            notices: list[TenderNotice] = []
            texts: list[str] = []
            for document in project.get("documents", []):
                notice = TenderNotice.model_validate(document.get("notice", {}))
                notices.append(notice)
                notice_texts = [notice.core_content]
                notice_texts.extend(
                    attachment.extracted_text
                    for attachment in notice.attachments
                    if attachment.extracted_text
                )
                texts.extend(notice_texts)
                source_text = "\n".join(notice_texts)
                for evidence in notice.evidence:
                    checked += 1
                    if _is_contained(evidence.quote, source_text):
                        supported += 1
                    else:
                        unsupported.append(
                            f"{project_id} 证据 {evidence.evidence_id} 的引文无法在原文或附件中定位"
                        )
            project_notices[project_id] = notices
            project_texts[project_id] = "\n".join(texts)

        evidence_by_id = {
            str(item.get("evidence_id")): item
            for item in state.get("evidence", [])
            if item.get("evidence_id")
        }
        for analysis in state.get("analysis", []):
            project_id = str(analysis.get("project_id", ""))
            project_issues: list[str] = []
            for evidence_id in analysis.get("evidence_ids", []):
                checked += 1
                evidence = evidence_by_id.get(str(evidence_id))
                if evidence is not None and str(evidence.get("project_id")) == project_id:
                    supported += 1
                else:
                    issue = f"{project_id} 引用了不存在或跨项目的证据 {evidence_id}"
                    unsupported.append(issue)
                    project_issues.append(issue)

            summary = analysis.get("summary")
            if summary:
                checked += 1
                if _is_contained(summary, project_texts.get(project_id, "")):
                    supported += 1
                else:
                    issue = f"{project_id} 摘要不是原文可定位片段"
                    unsupported.append(issue)
                    project_issues.append(issue)

            notices = project_notices.get(project_id, [])
            for field_name, value in (analysis.get("facts") or {}).items():
                if value is None:
                    continue
                checked += 1
                if self._field_has_source_support(notices, str(field_name), value):
                    supported += 1
                else:
                    issue = f"{project_id} 结构化字段 {field_name} 缺少可定位原文证据"
                    unsupported.append(issue)
                    project_issues.append(issue)

            project_results.append(
                {
                    "project_id": project_id,
                    "passed": not project_issues,
                    "issues": project_issues,
                }
            )

        return FactConsistencyResult(
            passed=checked > 0 and not unsupported,
            checked_claims=checked,
            supported_claims=supported,
            unsupported_claims=tuple(dict.fromkeys(unsupported)),
            project_results=tuple(project_results),
        )

    @staticmethod
    def _field_has_source_support(
        notices: list[TenderNotice],
        field_name: str,
        value: Any,
    ) -> bool:
        for notice in notices:
            source_value = getattr(notice, field_name, None)
            if source_value is None:
                continue
            if _normalized(source_value) != _normalized(value):
                continue
            for evidence in notice.evidence:
                if evidence.field_path == field_name and evidence.quote:
                    return True
        return False
