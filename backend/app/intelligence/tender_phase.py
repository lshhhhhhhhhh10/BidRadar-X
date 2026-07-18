from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from ..schemas.tender import TenderNotice


_TERMINAL_TITLE_PATTERNS = (
    r"(?:中标|成交|废标|流标|终止|取消|未成交).*(?:公告|公示|通知)",
    r"中标(?:候选人)?(?:结果)?(?:公告|公示|通知)",
    r"成交(?:结果)?(?:公告|公示|通知)",
    r"采购结果公告",
    r"结果公示",
    r"定标(?:结果)?(?:公告|公示)",
    r"合同公告",
    r"废标(?:公告|公示)",
    r"流标(?:公告|公示)",
    r"终止(?:公告|公示)",
    r"取消(?:公告|公示)",
    r"采购失败(?:公告|公示)",
    r"未成交(?:公告|公示)",
)

_TERMINAL_BODY_HEADINGS = (
    "中标（成交）结果公告",
    "中标(成交)结果公告",
    "中标结果公告",
    "成交结果公告",
    "采购结果公告",
    "废标公告",
    "流标公告",
    "终止公告",
    "采购失败公告",
)


@dataclass(frozen=True)
class TenderPhaseDecision:
    accepted: bool
    reason: str


def evaluate_tender_phase(
    notice: TenderNotice,
    *,
    as_of: datetime | None = None,
) -> TenderPhaseDecision:
    """Keep only opportunities that can still be tendered at collection time.

    This is deliberately deterministic and runs before semantic relevance review:
    an AI decision can never re-introduce an awarded, cancelled, or expired notice.
    """

    reference_time = as_of or notice.fetched_at
    if notice.notice_type in {"award", "cancellation"}:
        return TenderPhaseDecision(False, f"notice_type={notice.notice_type}")

    normalized_title = re.sub(r"\s+", "", notice.title)
    if any(re.search(pattern, normalized_title) for pattern in _TERMINAL_TITLE_PATTERNS):
        return TenderPhaseDecision(False, "terminal_title")

    body_heading = re.sub(r"\s+", "", notice.core_content[:600])
    if any(heading in body_heading for heading in _TERMINAL_BODY_HEADINGS):
        return TenderPhaseDecision(False, "terminal_body_heading")

    if notice.deadline is not None and notice.deadline <= reference_time:
        return TenderPhaseDecision(False, "deadline_passed")

    if notice.notice_type not in {"tender", "correction"}:
        return TenderPhaseDecision(False, f"unsupported_notice_type={notice.notice_type}")

    return TenderPhaseDecision(True, "active_tender")
