"""Add persisted minute-interval schedules without weakening existing constraints."""

from __future__ import annotations

import sqlite3


CHECKSUM = "interval-subscriptions-v1"


def upgrade(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE subscriptions_v0009 (
            task_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            frequency TEXT NOT NULL CHECK(frequency IN ('once', 'interval', 'daily', 'weekly')),
            interval_minutes INTEGER,
            timezone TEXT NOT NULL,
            local_time TEXT NOT NULL,
            weekly_day TEXT,
            run_at TEXT,
            next_run_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active', 'paused', 'completed', 'failed')),
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            retry_backoff_seconds INTEGER NOT NULL DEFAULT 30,
            last_run_at TEXT,
            last_error TEXT,
            lease_owner TEXT,
            lease_expires_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK(
                (frequency = 'interval' AND interval_minutes BETWEEN 3 AND 1440)
                OR (frequency != 'interval' AND interval_minutes IS NULL)
            )
        )
        """
    )
    connection.execute(
        """
        INSERT INTO subscriptions_v0009(
            task_id, query, frequency, interval_minutes, timezone, local_time,
            weekly_day, run_at, next_run_at, status, retry_count, max_retries,
            retry_backoff_seconds, last_run_at, last_error, lease_owner,
            lease_expires_at, created_at, updated_at
        )
        SELECT
            task_id, query, frequency, NULL, timezone, local_time,
            weekly_day, run_at, next_run_at, status, retry_count, max_retries,
            retry_backoff_seconds, last_run_at, last_error, lease_owner,
            lease_expires_at, created_at, updated_at
        FROM subscriptions
        """
    )
    connection.execute("DROP TABLE subscriptions")
    connection.execute("ALTER TABLE subscriptions_v0009 RENAME TO subscriptions")
    connection.execute(
        "CREATE INDEX idx_subscriptions_due "
        "ON subscriptions(status, next_run_at, lease_expires_at)"
    )
