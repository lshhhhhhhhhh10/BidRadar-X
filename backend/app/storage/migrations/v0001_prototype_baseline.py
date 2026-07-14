"""Capture and upgrade the pre-F02 prototype schema without losing rows."""

from __future__ import annotations

import sqlite3


CHECKSUM = "5ee2f93403eb0934e0e1f5af3bd54fb763ec292413859ce65420433823fc331a"


CREATE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY,
        query TEXT NOT NULL,
        frequency TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        status TEXT NOT NULL,
        result_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_snapshots (
        task_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        facts_json TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (task_id, project_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_profiles (
        run_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        project_json TEXT NOT NULL,
        modules_json TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (run_id, project_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_watermarks (
        task_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        watermark_json TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (task_id, source_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notice_snapshots (
        task_id TEXT NOT NULL,
        project_stable_fingerprint TEXT NOT NULL,
        notice_stable_fingerprint TEXT NOT NULL,
        snapshot_fingerprint TEXT NOT NULL,
        version INTEGER NOT NULL,
        notice_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (task_id, notice_stable_fingerprint, version),
        UNIQUE (task_id, notice_stable_fingerprint, snapshot_fingerprint)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS deliveries (
        delivery_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        delivery_type TEXT NOT NULL,
        delivery_fingerprint TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL CHECK(status IN ('pending', 'generated', 'delivered', 'failed')),
        project_fingerprints_json TEXT NOT NULL DEFAULT '[]',
        notice_fingerprints_json TEXT NOT NULL DEFAULT '[]',
        changes_json TEXT NOT NULL,
        artifact_uri TEXT,
        error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        generated_at TEXT,
        delivered_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS subscriptions (
        task_id TEXT PRIMARY KEY,
        query TEXT NOT NULL,
        frequency TEXT NOT NULL CHECK(frequency IN ('once', 'daily', 'weekly')),
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
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS schedule_runs (
        run_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        scheduled_for TEXT NOT NULL,
        worker_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('running', 'succeeded', 'failed', 'lease_expired')),
        retry_count INTEGER NOT NULL,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        error TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_deliveries_task_created ON deliveries(task_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_subscriptions_due ON subscriptions(status, next_run_at, lease_expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_schedule_runs_task_started ON schedule_runs(task_id, started_at)",
)


def upgrade(connection: sqlite3.Connection) -> None:
    for statement in CREATE_STATEMENTS:
        connection.execute(statement)
    _add_missing_columns(
        connection,
        "project_snapshots",
        {
            "project_stable_fingerprint": "TEXT",
            "snapshot_fingerprint": "TEXT",
            "snapshot_json": "TEXT",
            "version": "INTEGER NOT NULL DEFAULT 0",
        },
    )
    _add_missing_columns(
        connection,
        "deliveries",
        {
            "project_fingerprints_json": "TEXT NOT NULL DEFAULT '[]'",
            "notice_fingerprints_json": "TEXT NOT NULL DEFAULT '[]'",
        },
    )


def _add_missing_columns(
    connection: sqlite3.Connection,
    table: str,
    columns: dict[str, str],
) -> None:
    existing = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, declaration in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
