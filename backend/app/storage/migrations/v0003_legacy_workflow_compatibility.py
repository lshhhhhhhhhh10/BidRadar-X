"""Keep historical records compatible with legacy direct workflow invocation."""

from __future__ import annotations

import sqlite3


CHECKSUM = "58a25274179c08c1cb9cedf86cbe91f980ed441c4b60c9bb81fabffde44ea605"


def upgrade(connection: sqlite3.Connection) -> None:
    connection.execute(
        "ALTER TABLE project_snapshot_versions RENAME TO project_snapshot_versions_v2"
    )
    connection.execute(
        """
        CREATE TABLE project_snapshot_versions (
            snapshot_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            collection_run_id TEXT,
            snapshot_fingerprint TEXT NOT NULL,
            version INTEGER NOT NULL CHECK(version >= 1),
            snapshot_json TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            CHECK(length(snapshot_fingerprint) = 64),
            CHECK(snapshot_fingerprint NOT GLOB '*[^0-9a-f]*'),
            UNIQUE(task_id, project_id, snapshot_fingerprint),
            UNIQUE(task_id, project_id, version),
            FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE RESTRICT,
            FOREIGN KEY(collection_run_id) REFERENCES collection_runs(collection_run_id) ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO project_snapshot_versions(
            snapshot_id, task_id, project_id, collection_run_id,
            snapshot_fingerprint, version, snapshot_json, captured_at
        )
        SELECT snapshot_id, task_id, project_id, collection_run_id,
               snapshot_fingerprint, version, snapshot_json, captured_at
        FROM project_snapshot_versions_v2
        """
    )
    connection.execute("DROP TABLE project_snapshot_versions_v2")
    connection.execute(
        """
        CREATE INDEX idx_snapshot_versions_task_project
        ON project_snapshot_versions(task_id, project_id, version)
        """
    )

    connection.execute(
        "ALTER TABLE source_watermark_versions RENAME TO source_watermark_versions_v2"
    )
    connection.execute(
        """
        CREATE TABLE source_watermark_versions (
            watermark_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            collection_run_id TEXT,
            cursor_published_at TEXT NOT NULL,
            cursor_source_notice_id TEXT,
            cursor_source_url TEXT,
            cursor_notice_fingerprint TEXT,
            cursor_identity_fingerprint TEXT NOT NULL,
            watermark_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CHECK(
                cursor_source_notice_id IS NOT NULL
                OR cursor_source_url IS NOT NULL
                OR cursor_notice_fingerprint IS NOT NULL
            ),
            CHECK(length(cursor_identity_fingerprint) = 64),
            CHECK(cursor_identity_fingerprint NOT GLOB '*[^0-9a-f]*'),
            UNIQUE(task_id, source_id, cursor_identity_fingerprint),
            FOREIGN KEY(collection_run_id) REFERENCES collection_runs(collection_run_id) ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO source_watermark_versions(
            watermark_id, task_id, source_id, collection_run_id,
            cursor_published_at, cursor_source_notice_id, cursor_source_url,
            cursor_notice_fingerprint, cursor_identity_fingerprint,
            watermark_json, created_at
        )
        SELECT watermark_id, task_id, source_id, collection_run_id,
               cursor_published_at, cursor_source_notice_id, cursor_source_url,
               cursor_notice_fingerprint, cursor_identity_fingerprint,
               watermark_json, created_at
        FROM source_watermark_versions_v2
        """
    )
    connection.execute("DROP TABLE source_watermark_versions_v2")
    connection.execute(
        """
        CREATE INDEX idx_watermark_versions_task_source
        ON source_watermark_versions(task_id, source_id, created_at)
        """
    )
