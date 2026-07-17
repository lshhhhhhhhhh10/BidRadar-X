from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.services.spend_guard import DailyBudgetExceededError, DailySpendGuard


class DailySpendGuardTest(unittest.TestCase):
    def test_aborts_before_next_paid_call_would_exceed_daily_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "app.storage.database.DATABASE_PATH", Path(directory) / "spend.db"
        ):
            guard = DailySpendGuard(
                clock=lambda: datetime(2026, 7, 17, 22, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
            )
            guard.set_daily_limit("0.20")
            first = guard.charge(provider="paid-source", amount="0.20", detail="test")

            self.assertEqual(str(first.spent_today), "0.2")
            with self.assertRaises(DailyBudgetExceededError):
                guard.charge(provider="paid-source", amount="0.20", detail="blocked")

            snapshot = guard.snapshot()
            self.assertEqual(str(snapshot.spent_today), "0.2")
            self.assertEqual(str(snapshot.remaining), "0")


if __name__ == "__main__":
    unittest.main()
