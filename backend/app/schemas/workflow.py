from typing import Any, TypedDict


class WorkflowState(TypedDict, total=False):
    task_id: str
    run_id: str
    query: str
    frequency: str
    status: str
    task_spec: dict[str, Any]
    monitor_plan: dict[str, Any]
    search_plan: dict[str, Any]
    selected_sources: list[dict[str, Any]]
    raw_documents: list[dict[str, Any]]
    normalized_documents: list[dict[str, Any]]
    relevant_documents: list[dict[str, Any]]
    projects: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    analysis: list[dict[str, Any]]
    changes: list[dict[str, Any]]
    steps: list[dict[str, Any]]
    funnel: dict[str, int]
    quality_passed: bool
    quality_issues: list[str]
    retry_count: int
    report: dict[str, Any]
