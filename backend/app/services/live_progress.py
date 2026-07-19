from __future__ import annotations

import re
from typing import Any

from .source_failures import source_failure_reason


_STAGE_DEFINITIONS = (
    ("intent", "理解检索意图", "task_spec", {"intent-extraction"}),
    ("expansion", "扩展同义词与相关词", "query_expansion", {"query-expansion"}),
    ("sources", "检索已接入信息源", "relevant_documents", {"search-planning"}),
    (
        "cleaning",
        "清洗、审核与查重",
        "changes",
        {"relevance-review", "ambiguous-deduplication", "fact-verification"},
    ),
    ("documents", "生成项目 Word 文档", "report", {"evidence-report"}),
)


def build_live_progress(
    state: dict[str, Any],
    *,
    lifecycle: str = "running",
    error_message: str | None = None,
) -> dict[str, Any]:
    """Build a public, evidence-backed five-stage view from workflow state.

    The returned state never guesses that a stage succeeded. Collection and
    cleaning are marked empty when the workflow found no relevant projects,
    and AI badges are derived exclusively from persisted AI audit records.
    """

    done = [completion_key in state for _, _, completion_key, _ in _STAGE_DEFINITIONS]
    try:
        current_index = done.index(False)
    except ValueError:
        current_index = -1

    stages: list[dict[str, Any]] = []
    for index, (stage_id, title, _, prompt_ids) in enumerate(_STAGE_DEFINITIONS):
        status = _stage_status(
            stage_id,
            state,
            done=done[index],
            is_current=index == current_index,
            lifecycle=lifecycle,
        )
        details, summary = _stage_details(stage_id, state)
        stages.append(
            {
                "id": stage_id,
                "number": index + 1,
                "title": title,
                "status": status,
                "summary": summary,
                "details": details,
                "ai": _ai_evidence(state.get("ai_audit", []), prompt_ids),
            }
        )

    return {
        "status": lifecycle,
        "run_id": state.get("run_id"),
        "task_id": state.get("task_id"),
        "project_count": len(state.get("projects", [])),
        "stages": stages,
        "error_message": error_message,
    }


def _stage_status(
    stage_id: str,
    state: dict[str, Any],
    *,
    done: bool,
    is_current: bool,
    lifecycle: str,
) -> str:
    if not done:
        if is_current and lifecycle in {"running", "pausing"}:
            return "running"
        if is_current and lifecycle == "failed":
            return "error"
        return "pending"

    if stage_id == "sources":
        selected = state.get("selected_sources", [])
        if selected and all(item.get("collection_status") == "failed" for item in selected):
            return "error"
        if "relevant_documents" in state and not state.get("relevant_documents"):
            return "empty"
        if not state.get("raw_documents"):
            return "empty"
    elif stage_id == "cleaning" and not state.get("projects"):
        return "empty"
    elif stage_id == "documents":
        if not state.get("projects"):
            return "empty"
        if state.get("report", {}).get("status") not in {"generated", "no_change"}:
            return "error"
    return "success"


def _stage_details(stage_id: str, state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if stage_id == "intent":
        spec = state.get("task_spec", {})
        fields = [
            {"label": "主题", "value": spec.get("topic") or state.get("query") or "识别中"},
            {"label": "地区", "value": "、".join(spec.get("regions", [])) or "全国"},
            {"label": "时间", "value": _date_range(spec)},
            {"label": "频率", "value": _frequency_label(spec.get("schedule") or state.get("frequency"))},
            {"label": "排除", "value": "、".join(spec.get("exclusions", [])) or "无"},
        ]
        return {"fields": fields}, _field_summary(fields, "正在识别检索条件")

    if stage_id == "expansion":
        expansion = state.get("query_expansion", {})
        original = expansion.get("original_keywords", [])
        added = expansion.get("added_keywords", [])
        phrases = expansion.get("search_phrases", [])
        summary = (
            f"新增：{' · '.join(str(item) for item in added[:4])}"
            if added
            else expansion.get("summary") or "正在生成检索词"
        )
        return {
            "original_keywords": original,
            "added_keywords": added,
            "search_phrases": phrases,
            "negative_terms": expansion.get("negative_terms", []),
        }, summary

    if stage_id == "sources":
        relevant_by_source: dict[str, int] = {}
        for document in state.get("relevant_documents", []):
            source = document.get("source") if isinstance(document, dict) else None
            source_id = str(
                document.get("source_id")
                or (source.get("source_id") if isinstance(source, dict) else "")
                or ""
            )
            relevant_by_source[source_id] = relevant_by_source.get(source_id, 0) + 1
        relevance_finished = "relevant_documents" in state
        sources = []
        for item in state.get("selected_sources", []):
            collected = int(item.get("record_count") or 0)
            relevant = relevant_by_source.get(str(item.get("source_id") or ""), 0)
            collection_status = item.get("collection_status", "pending")
            if collection_status == "failed":
                result = "failed"
            elif relevance_finished and relevant == 0:
                result = "empty"
            elif collection_status == "success" and collected > 0:
                result = "success"
            elif collection_status == "success":
                result = "empty"
            else:
                result = "pending"
            sources.append(
                {
                    "source_id": item.get("source_id"),
                    "name": item.get("name") or item.get("source_id") or "未知来源",
                    "status": result,
                    "collected_count": collected,
                    "relevant_count": relevant if relevance_finished else None,
                    "requires_login": bool(item.get("requires_login")),
                    "failure_reason": (
                        item.get("failure_reason") or source_failure_reason(item)
                        if result == "failed"
                        else None
                    ),
                    "attempt_count": int(item.get("attempt_count") or 0),
                }
            )
        successful = sum(item["status"] == "success" for item in sources)
        relevant_count = len(state.get("relevant_documents", []))
        if relevance_finished:
            successful_names = "、".join(item["name"] for item in sources if item["status"] == "success")
            summary = (
                f"{successful_names or f'{successful} 个网站'}：{relevant_count} 条相关内容"
                if relevant_count
                else "已检查所有信息源，未找到相关内容"
            )
        elif "raw_documents" in state:
            summary = f"抓取 {len(state.get('raw_documents', []))} 条候选内容，等待相关性审核"
        else:
            summary = "正在逐个访问已接入的信息源"
        return {"sources": sources}, summary

    if stage_id == "cleaning":
        funnel = state.get("funnel", {})
        counts = [
            {"label": "原始候选", "value": int(funnel.get("raw", 0))},
            {"label": "在招项目", "value": int(funnel.get("active_tender", 0))},
            {"label": "相关内容", "value": int(funnel.get("relevant", 0))},
            {"label": "去重后项目", "value": int(funnel.get("projects", 0))},
            {"label": "合并镜像", "value": int(funnel.get("mirrors", 0))},
        ]
        if "changes" in state:
            project_count = len(state.get("projects", []))
            summary = f"清洗查重完成，保留 {project_count} 个有效项目" if project_count else "清洗完成，没有可保留的在招项目"
        else:
            summary = "正在排除已中标、已流标和重复内容"
        return {"counts": counts, "quality_issues": state.get("quality_issues", [])}, summary

    report = state.get("report", {})
    documents = report.get("project_documents", []) or report.get("documents", []) or []
    if "report" not in state:
        summary = "正在根据已核验事实生成可下载文档"
    elif not state.get("projects"):
        summary = "未发现有效项目，不生成空 Word 文档"
    elif report.get("status") == "generated":
        summary = f"已生成 {len(documents) or len(state.get('projects', []))} 份 Word 文档"
    else:
        summary = "Word 文档生成失败"
    return {
        "report_status": report.get("status", "pending"),
        "document_count": len(documents),
    }, summary


def _ai_evidence(audits: list[dict[str, Any]], prompt_ids: set[str]) -> dict[str, Any]:
    matches = [item for item in audits if item.get("prompt_id") in prompt_ids]
    completed = [item for item in matches if item.get("status") == "completed"]
    latest = completed[-1] if completed else (matches[-1] if matches else {})
    if completed:
        label = "AI 已真实调用"
        status = "completed"
    elif matches:
        label = "AI 未成功，已使用规则兜底"
        status = latest.get("status", "failed")
    else:
        label = "等待 AI 调用"
        status = "pending"
    return {
        "status": status,
        "label": label,
        "model": latest.get("model"),
        "latency_ms": latest.get("latency_ms"),
        "call_count": len(completed),
        "failure_reason": latest.get("failure_reason"),
        "provider_code": latest.get("provider_code"),
    }


def _date_range(spec: dict[str, Any]) -> str:
    start = spec.get("time_range_start") or spec.get("start_date") or spec.get("date_from")
    end = spec.get("time_range_end") or spec.get("end_date") or spec.get("date_to")
    if start and end:
        return f"{start} 至 {end}"
    return str(start or end or "不限")


def _frequency_label(value: Any) -> str:
    mapping = {"once": "单次", "daily": "每日", "weekly": "每周"}
    if isinstance(value, dict):
        frequency = value.get("frequency") or value.get("type")
        if frequency == "interval":
            return f"每 {value.get('interval_minutes') or 3} 分钟"
        value = frequency
    if value == "interval":
        return "按分钟间隔"
    return mapping.get(str(value), str(value or "单次"))


def _field_summary(fields: list[dict[str, Any]], fallback: str) -> str:
    if not fields or any(item["value"] == "识别中" for item in fields):
        return fallback
    return " · ".join(f"{item['label']} {item['value']}" for item in fields[:3])
