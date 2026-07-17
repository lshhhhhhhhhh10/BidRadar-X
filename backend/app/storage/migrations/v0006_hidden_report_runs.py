"""Allow users to hide report-history entries without deleting evidence."""

from __future__ import annotations

import sqlite3


CHECKSUM = "9bdb53793d2e2c8d5cf24ca9f62e3c654879f446949b13feae9d8036fbfb3341"


def upgrade(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE hidden_report_runs (
            run_id TEXT PRIMARY KEY,
            hidden_at TEXT NOT NULL
        )
        """
    )
