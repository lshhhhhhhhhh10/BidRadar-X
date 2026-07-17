"""Atomic daily spending guard used before every paid provider request."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from zoneinfo import ZoneInfo

from ..storage.database import connect, initialize_database


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
FEN = Decimal("0.01")


class DailyBudgetExceededError(RuntimeError):
    """The next paid call would exceed the persisted daily limit."""


@dataclass(frozen=True)
class SpendSnapshot:
    daily_limit: Decimal
    spent_today: Decimal
    remaining: Decimal
    currency: str = "CNY"
    enforced: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "daily_limit": f"{self.daily_limit:.2f}",
            "spent_today": f"{self.spent_today:.2f}",
            "remaining": f"{self.remaining:.2f}",
            "currency": self.currency,
            "enforced": self.enforced,
        }


class DailySpendGuard:
    """Reserve cost synchronously before transport so concurrent calls cannot race."""

    def __init__(self, *, clock=None) -> None:
        initialize_database()
        self._clock = clock or (lambda: datetime.now(SHANGHAI_TZ))

    def snapshot(self) -> SpendSnapshot:
        local_day = self._local_day()
        with connect() as connection:
            limit_fen = int(
                connection.execute(
                    "SELECT daily_limit_fen FROM spend_policy WHERE singleton_id = 1"
                ).fetchone()[0]
            )
            spent_fen = int(
                connection.execute(
                    "SELECT COALESCE(SUM(amount_fen), 0) FROM spend_events WHERE local_day = ?",
                    (local_day,),
                ).fetchone()[0]
            )
        return _snapshot(limit_fen, spent_fen)

    def set_daily_limit(self, amount: Decimal | str | int | float) -> SpendSnapshot:
        limit_fen = _to_fen(amount)
        if limit_fen > 100_000_000:
            raise ValueError("daily limit is too large")
        now = self._now().isoformat(timespec="seconds")
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE spend_policy SET daily_limit_fen = ?, updated_at = ? WHERE singleton_id = 1",
                (limit_fen, now),
            )
            spent_fen = int(
                connection.execute(
                    "SELECT COALESCE(SUM(amount_fen), 0) FROM spend_events WHERE local_day = ?",
                    (self._local_day(),),
                ).fetchone()[0]
            )
        return _snapshot(limit_fen, spent_fen)

    def charge(
        self,
        *,
        provider: str,
        amount: Decimal | str | int | float,
        detail: str | None = None,
    ) -> SpendSnapshot:
        amount_fen = _to_fen(amount)
        if amount_fen <= 0:
            return self.snapshot()
        now = self._now()
        local_day = now.astimezone(SHANGHAI_TZ).date().isoformat()
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            limit_fen = int(
                connection.execute(
                    "SELECT daily_limit_fen FROM spend_policy WHERE singleton_id = 1"
                ).fetchone()[0]
            )
            spent_fen = int(
                connection.execute(
                    "SELECT COALESCE(SUM(amount_fen), 0) FROM spend_events WHERE local_day = ?",
                    (local_day,),
                ).fetchone()[0]
            )
            if spent_fen + amount_fen > limit_fen:
                connection.rollback()
                raise DailyBudgetExceededError(
                    "今日付费接口预算不足：下一次请求将超过每日上限，调用已在发送前强制中断。"
                )
            connection.execute(
                """
                INSERT INTO spend_events(event_id, provider, amount_fen, local_day, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    provider,
                    amount_fen,
                    local_day,
                    detail,
                    now.isoformat(timespec="seconds"),
                ),
            )
        return _snapshot(limit_fen, spent_fen + amount_fen)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value

    def _local_day(self) -> str:
        return self._now().astimezone(SHANGHAI_TZ).date().isoformat()


def _to_fen(value: Decimal | str | int | float) -> int:
    amount = Decimal(str(value)).quantize(FEN, rounding=ROUND_HALF_UP)
    if amount < 0:
        raise ValueError("amount must not be negative")
    return int(amount * 100)


def _snapshot(limit_fen: int, spent_fen: int) -> SpendSnapshot:
    remaining_fen = max(0, limit_fen - spent_fen)
    return SpendSnapshot(
        daily_limit=Decimal(limit_fen) / 100,
        spent_today=Decimal(spent_fen) / 100,
        remaining=Decimal(remaining_fen) / 100,
    )


__all__ = ["DailyBudgetExceededError", "DailySpendGuard", "SpendSnapshot"]
