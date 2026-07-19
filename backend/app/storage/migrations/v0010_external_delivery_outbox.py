"""Persist external delivery attempts independently from workflow execution."""

from __future__ import annotations

import sqlite3


CHECKSUM = "external-delivery-outbox-v1"


def upgrade(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE external_delivery_outbox (
            event_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            task_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK(status IN ('pending', 'sending', 'delivered', 'failed')),
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 10,
            next_attempt_at TEXT NOT NULL,
            lease_owner TEXT,
            lease_expires_at TEXT,
            remote_record_id TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_external_delivery_due
        ON external_delivery_outbox(provider, status, next_attempt_at, lease_expires_at)
        """
    )
