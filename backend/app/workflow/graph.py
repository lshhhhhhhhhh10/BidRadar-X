from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from ..schemas.workflow import WorkflowState
from .nodes.change import detect_changes
from .nodes.collect import collect_documents
from .nodes.evidence import build_evidence
from .nodes.feedback import update_memory
from .nodes.normalize import normalize_documents
from .nodes.project_merge import merge_projects
from .nodes.rag import analyze_with_rag
from .nodes.relevance import judge_relevance
from .nodes.report import generate_report
from .nodes.requirement import understand_requirement
from .nodes.search_plan import plan_search
from .nodes.source_select import select_sources
from .nodes.task_plan import plan_task
from .nodes.timeline import build_timeline
from .nodes.verify import verify_facts


def _quality_route(state: dict[str, Any]) -> str:
    if state["quality_passed"] or state.get("retry_count", 0) > 1:
        return "change"
    return "retry"


def build_workflow():
    builder = StateGraph(WorkflowState)
    builder.add_node("requirement", understand_requirement)
    builder.add_node("task_plan", plan_task)
    builder.add_node("search_plan", plan_search)
    builder.add_node("source_select", select_sources)
    builder.add_node("collect", collect_documents)
    builder.add_node("normalize", normalize_documents)
    builder.add_node("relevance", judge_relevance)
    builder.add_node("project_merge", merge_projects)
    builder.add_node("timeline", build_timeline)
    builder.add_node("evidence", build_evidence)
    builder.add_node("rag", analyze_with_rag)
    builder.add_node("verify", verify_facts)
    builder.add_node("change", detect_changes)
    builder.add_node("report", generate_report)
    builder.add_node("feedback", update_memory)

    builder.add_edge(START, "requirement")
    builder.add_edge("requirement", "task_plan")
    builder.add_edge("task_plan", "search_plan")
    builder.add_edge("search_plan", "source_select")
    builder.add_edge("source_select", "collect")
    builder.add_edge("collect", "normalize")
    builder.add_edge("normalize", "relevance")
    builder.add_edge("relevance", "project_merge")
    builder.add_edge("project_merge", "timeline")
    builder.add_edge("timeline", "evidence")
    builder.add_edge("evidence", "rag")
    builder.add_edge("rag", "verify")
    builder.add_conditional_edges("verify", _quality_route, {"retry": "search_plan", "change": "change"})
    builder.add_edge("change", "report")
    builder.add_edge("report", "feedback")
    builder.add_edge("feedback", END)
    return builder.compile()


WORKFLOW = build_workflow()


WORKFLOW_DEFINITION = [
    "需求理解 Agent",
    "监控任务与约束计划",
    "检索规划 Agent",
    "成本感知来源路由",
    "多源采集 Agent 集群",
    "内容解析与标准化",
    "相关性判断 Agent",
    "项目实体归并与跨站去重",
    "项目事件图谱与时序记忆",
    "证据知识库",
    "Agentic Evidence RAG",
    "事实核验 Agent",
    "字段级时序变化检测",
    "报告生成 Agent",
    "用户反馈与长期记忆",
]
