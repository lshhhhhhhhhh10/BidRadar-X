"""Add normalized identities, provenance, collection, and audit history."""

from __future__ import annotations

import sqlite3


CHECKSUM = "27d71666bc2cb12275f2afd24b6964ecb8130c6fd64ba24034495f14b8f59d72"


CREATE_STATEMENTS = (
    """
    CREATE TABLE projects (
        project_id TEXT PRIMARY KEY,
        project_stable_fingerprint TEXT NOT NULL UNIQUE,
        fingerprint_version TEXT NOT NULL,
        created_at TEXT NOT NULL,
        CHECK(length(project_stable_fingerprint) = 64),
        CHECK(project_stable_fingerprint NOT GLOB '*[^0-9a-f]*')
    )
    """,
    """
    CREATE TABLE notice_events (
        notice_event_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        notice_stable_fingerprint TEXT NOT NULL UNIQUE,
        fingerprint_version TEXT NOT NULL,
        notice_type TEXT NOT NULL CHECK(notice_type IN ('tender', 'correction', 'award', 'cancellation', 'other')),
        project_code TEXT,
        created_at TEXT NOT NULL,
        CHECK(length(notice_stable_fingerprint) = 64),
        CHECK(notice_stable_fingerprint NOT GLOB '*[^0-9a-f]*'),
        FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE collection_runs (
        collection_run_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('running', 'succeeded', 'failed')),
        started_at TEXT NOT NULL,
        completed_at TEXT,
        error_code TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(task_id, source_id, idempotency_key),
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE source_publications (
        publication_id TEXT PRIMARY KEY,
        notice_id TEXT NOT NULL,
        notice_event_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        source_name TEXT NOT NULL,
        source_url TEXT NOT NULL,
        canonical_notice_url TEXT,
        source_notice_id TEXT,
        publication_role TEXT NOT NULL CHECK(publication_role IN ('original', 'republication')),
        title TEXT NOT NULL,
        published_at TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        core_content TEXT NOT NULL,
        raw_content_fingerprint TEXT NOT NULL,
        response_http_status INTEGER,
        response_content_type TEXT,
        response_etag TEXT,
        response_last_modified TEXT,
        response_metadata_json TEXT,
        created_at TEXT NOT NULL,
        CHECK(length(raw_content_fingerprint) = 64),
        CHECK(raw_content_fingerprint NOT GLOB '*[^0-9a-f]*'),
        UNIQUE(source_id, notice_id, raw_content_fingerprint),
        UNIQUE(source_id, source_url, raw_content_fingerprint),
        FOREIGN KEY(notice_event_id) REFERENCES notice_events(notice_event_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE collection_run_publications (
        collection_run_id TEXT NOT NULL,
        publication_id TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        PRIMARY KEY(collection_run_id, publication_id),
        FOREIGN KEY(collection_run_id) REFERENCES collection_runs(collection_run_id) ON DELETE RESTRICT,
        FOREIGN KEY(publication_id) REFERENCES source_publications(publication_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE attachments (
        attachment_pk TEXT PRIMARY KEY,
        attachment_id TEXT NOT NULL,
        publication_id TEXT NOT NULL,
        entry_url TEXT NOT NULL,
        name TEXT,
        status TEXT NOT NULL CHECK(status IN ('discovered', 'download_allowed', 'downloaded', 'blocked', 'restricted', 'invalid', 'failed')),
        media_type TEXT,
        size_bytes INTEGER CHECK(size_bytes IS NULL OR size_bytes >= 0),
        content_sha256 TEXT,
        fetched_at TEXT,
        failure_reason TEXT,
        created_at TEXT NOT NULL,
        CHECK(content_sha256 IS NULL OR (length(content_sha256) = 64 AND content_sha256 NOT GLOB '*[^0-9a-f]*')),
        UNIQUE(publication_id, attachment_id),
        UNIQUE(attachment_id, publication_id),
        UNIQUE(publication_id, entry_url),
        FOREIGN KEY(publication_id) REFERENCES source_publications(publication_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE field_evidence (
        evidence_pk TEXT PRIMARY KEY,
        evidence_id TEXT NOT NULL,
        publication_id TEXT NOT NULL,
        notice_event_id TEXT NOT NULL,
        attachment_id TEXT,
        field_path TEXT NOT NULL,
        source_url TEXT NOT NULL,
        document_name TEXT,
        page_number INTEGER CHECK(page_number IS NULL OR page_number >= 1),
        section TEXT,
        locator TEXT,
        quote TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(publication_id, evidence_id),
        FOREIGN KEY(publication_id) REFERENCES source_publications(publication_id) ON DELETE RESTRICT,
        FOREIGN KEY(notice_event_id) REFERENCES notice_events(notice_event_id) ON DELETE RESTRICT,
        FOREIGN KEY(attachment_id, publication_id) REFERENCES attachments(attachment_id, publication_id) ON DELETE RESTRICT
    )
    """,
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
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE RESTRICT,
        FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE RESTRICT,
        FOREIGN KEY(collection_run_id) REFERENCES collection_runs(collection_run_id) ON DELETE RESTRICT
    )
    """,
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
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE RESTRICT,
        FOREIGN KEY(collection_run_id) REFERENCES collection_runs(collection_run_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE run_versions (
        run_version_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        version INTEGER NOT NULL CHECK(version >= 1),
        status TEXT NOT NULL,
        result_fingerprint TEXT NOT NULL,
        result_json TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        UNIQUE(run_id, version),
        UNIQUE(run_id, result_fingerprint),
        FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE delivery_events (
        event_id TEXT PRIMARY KEY,
        delivery_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending', 'generated', 'delivered', 'failed')),
        run_id TEXT NOT NULL,
        artifact_uri TEXT,
        error TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(delivery_id) REFERENCES deliveries(delivery_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE delivery_change_versions (
        change_version_id TEXT PRIMARY KEY,
        delivery_id TEXT NOT NULL,
        change_fingerprint TEXT NOT NULL,
        changes_json TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        UNIQUE(delivery_id, change_fingerprint),
        FOREIGN KEY(delivery_id) REFERENCES deliveries(delivery_id) ON DELETE RESTRICT
    )
    """,
    "CREATE INDEX idx_notice_events_project ON notice_events(project_id)",
    "CREATE INDEX idx_publications_event ON source_publications(notice_event_id, published_at)",
    "CREATE INDEX idx_attachments_publication ON attachments(publication_id)",
    "CREATE INDEX idx_evidence_publication_field ON field_evidence(publication_id, field_path)",
    "CREATE INDEX idx_collection_runs_task_started ON collection_runs(task_id, started_at)",
    "CREATE INDEX idx_snapshot_versions_task_project ON project_snapshot_versions(task_id, project_id, version)",
    "CREATE INDEX idx_watermark_versions_task_source ON source_watermark_versions(task_id, source_id, created_at)",
    "CREATE INDEX idx_delivery_events_delivery ON delivery_events(delivery_id, created_at)",
)


def upgrade(connection: sqlite3.Connection) -> None:
    for statement in CREATE_STATEMENTS:
        connection.execute(statement)
