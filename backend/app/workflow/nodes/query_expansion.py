from __future__ import annotations

import re
from typing import Any

from ...ai.service import AICoordinator, append_audit
from ...schemas.tender import TaskSpec
from .common import step


EXPANSION_DICTIONARY = {
    "服务器": [
        "机架式服务器",
        "刀片服务器",
        "GPU服务器",
        "计算服务器",
        "计算节点",
        "存储服务器",
        "超融合一体机",
        "服务器集群",
    ],
    "人工智能": [
        "AI平台",
        "大模型平台",
        "智能计算",
        "机器学习平台",
        "训练集群",
        "推理集群",
        "算力平台",
    ],
    "充电桩": [
        "充电设施",
        "充电站",
        "充电基础设施",
        "交流充电桩",
        "直流充电桩",
        "新能源车充电设备",
    ],
}


def _safe_term(value: str) -> str | None:
    term = re.sub(r"\s+", " ", value).strip(" ,，;；。")
    if not 1 <= len(term) <= 40 or "http://" in term or "https://" in term:
        return None
    return term


def _unique_terms(values: list[str], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = _safe_term(value)
        if term is None or term.casefold() in seen:
            continue
        seen.add(term.casefold())
        result.append(term)
        if len(result) >= limit:
            break
    return result


def _dictionary_expansion(topic: str, keywords: list[str]) -> list[str]:
    expanded: list[str] = []
    searchable = " ".join([topic, *keywords])
    for anchor, terms in EXPANSION_DICTIONARY.items():
        if anchor in searchable:
            expanded.extend(terms)
    return expanded


def expand_query(state: dict[str, Any]) -> dict[str, Any]:
    task_spec = TaskSpec.model_validate(state["task_spec"])
    dictionary_terms = _dictionary_expansion(task_spec.topic, task_spec.keywords)
    region = " ".join(task_spec.regions) or "全国"
    fallback_terms = _unique_terms(
        [*task_spec.keywords, *dictionary_terms],
        12,
    )
    fallback_phrases = _unique_terms(
        [f"{region} {term} 招标采购" for term in fallback_terms[:8]],
        8,
    )

    coordinator = AICoordinator()
    expansion, audit = coordinator.expand_query(
        {
            "original_query": task_spec.query,
            "understood_intent": {
                "topic": task_spec.topic,
                "regions": task_spec.regions,
                "keywords": task_spec.keywords,
                "exclusions": task_spec.exclusions,
            },
            "dictionary_fallback": {
                "terms": fallback_terms,
                "search_phrases": fallback_phrases,
            },
            "domain": "招标采购公告检索",
        }
    )
    ai_used = expansion is not None
    if expansion is not None:
        expanded_terms = _unique_terms(
            [
                *task_spec.keywords,
                *expansion.core_terms,
                *expansion.synonyms,
                *expansion.category_terms,
                *expansion.scenario_terms,
                *dictionary_terms,
            ],
            12,
        )
        negative_terms = _unique_terms(
            [*task_spec.exclusions, *expansion.negative_terms],
            16,
        )
        search_phrases = _unique_terms(
            [*expansion.search_phrases, *fallback_phrases],
            12,
        )
        summary = expansion.expansion_summary
    else:
        expanded_terms = fallback_terms
        negative_terms = task_spec.exclusions
        search_phrases = fallback_phrases
        summary = "使用本地采购词典扩展同义词、设备形态和采购场景。"

    updated_spec = task_spec.model_copy(
        update={"keywords": expanded_terms, "exclusions": negative_terms}
    )
    query_expansion = {
        "mode": "ai" if ai_used else "dictionary",
        "original_keywords": task_spec.keywords,
        "expanded_keywords": expanded_terms,
        "added_keywords": [
            item for item in expanded_terms if item not in task_spec.keywords
        ],
        "negative_terms": negative_terms,
        "search_phrases": search_phrases,
        "summary": summary,
    }
    return {
        "task_spec": updated_spec.model_dump(mode="json"),
        "query_expansion": query_expansion,
        "ai_audit": append_audit(state, audit),
        "steps": step(
            state,
            "检索扩词 Agent",
            f"{'AI' if ai_used else '本地词典'}将 {len(task_spec.keywords)} 个基础词扩展为 {len(expanded_terms)} 个检索词。",
            len(task_spec.keywords),
            len(expanded_terms),
        ),
    }
