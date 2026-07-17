"""Persist an atomic per-user daily spend ceiling for paid data sources."""

from __future__ import annotations

import sqlite3


CHECKSUM = "4d83872cc6f54a9e7c17440169541cc176741b776f8522eb6f7fc37527eab82e"


def upgrade(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE spend_policy (
            singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
            daily_limit_fen INTEGER NOT NULL CHECK (daily_limit_fen >= 0),
            updated_at TEXT NOT NULL
        );

        INSERT INTO spend_policy(singleton_id, daily_limit_fen, updated_at)
        VALUES (1, 2000, CURRENT_TIMESTAMP);

        CREATE TABLE spend_events (
            event_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            amount_fen INTEGER NOT NULL CHECK (amount_fen >= 0),
            local_day TEXT NOT NULL,
            detail TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX spend_events_day_idx
        ON spend_events(local_day, provider);
        """
    )
