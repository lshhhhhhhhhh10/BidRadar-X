"""Preserve complete contract payloads and auditable attachment state changes."""

from __future__ import annotations

import sqlite3


CHECKSUM = "d999a9cc6d1e3a63c51602bcf9da532de37f5ab48c22793ba73bd151c542c15e"


def upgrade(connection: sqlite3.Connection) -> None:
    rebuild_source_publication_graph(connection, identity_version=4)
    create_contract_history(connection)
    _create_task_identities(connection)
    _rebuild_task_scoped_history(connection)


def rebuild_source_publication_graph(
    connection: sqlite3.Connection,
    *,
    identity_version: int,
) -> None:
    if identity_version == 4:
        identity_constraints = """
            UNIQUE(source_id, notice_id, publication_role, raw_content_fingerprint),
            UNIQUE(source_id, source_url, publication_role, raw_content_fingerprint),
        """
    elif identity_version == 5:
        identity_constraints = """
            UNIQUE(
                source_id, notice_id, source_url,
                publication_role, raw_content_fingerprint
            ),
        """
    else:
        raise ValueError(f"unsupported source publication identity version: {identity_version}")
    connection.execute("ALTER TABLE source_publications RENAME TO source_publications_v2")
    connection.execute(
        "ALTER TABLE collection_run_publications RENAME TO collection_run_publications_v2"
    )
    connection.execute("ALTER TABLE attachments RENAME TO attachments_v2")
    connection.execute("ALTER TABLE field_evidence RENAME TO field_evidence_v2")

    connection.execute(
        f"""
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
            {identity_constraints}
            FOREIGN KEY(notice_event_id) REFERENCES notice_events(notice_event_id) ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO source_publications(
            publication_id, notice_id, notice_event_id, source_id, source_name,
            source_url, canonical_notice_url, source_notice_id, publication_role,
            title, published_at, fetched_at, core_content, raw_content_fingerprint,
            response_http_status, response_content_type, response_etag,
            response_last_modified, response_metadata_json, created_at
        )
        SELECT publication_id, notice_id, notice_event_id, source_id, source_name,
               source_url, canonical_notice_url, source_notice_id, publication_role,
               title, published_at, fetched_at, core_content, raw_content_fingerprint,
               response_http_status, response_content_type, response_etag,
               response_last_modified, response_metadata_json, created_at
        FROM source_publications_v2
        """
    )

    connection.execute(
        """
        CREATE TABLE collection_run_publications (
            collection_run_id TEXT NOT NULL,
            publication_id TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            PRIMARY KEY(collection_run_id, publication_id),
            FOREIGN KEY(collection_run_id) REFERENCES collection_runs(collection_run_id) ON DELETE RESTRICT,
            FOREIGN KEY(publication_id) REFERENCES source_publications(publication_id) ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO collection_run_publications(collection_run_id, publication_id, observed_at)
        SELECT collection_run_id, publication_id, observed_at
        FROM collection_run_publications_v2
        """
    )

    connection.execute(
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
        """
    )
    connection.execute(
        """
        INSERT INTO attachments(
            attachment_pk, attachment_id, publication_id, entry_url, name,
            status, media_type, size_bytes, content_sha256, fetched_at,
            failure_reason, created_at
        )
        SELECT attachment_pk, attachment_id, publication_id, entry_url, name,
               status, media_type, size_bytes, content_sha256, fetched_at,
               failure_reason, created_at
        FROM attachments_v2
        """
    )

    connection.execute(
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
        """
    )
    connection.execute(
        """
        INSERT INTO field_evidence(
            evidence_pk, evidence_id, publication_id, notice_event_id,
            attachment_id, field_path, source_url, document_name, page_number,
            section, locator, quote, fetched_at, created_at
        )
        SELECT evidence_pk, evidence_id, publication_id, notice_event_id,
               attachment_id, field_path, source_url, document_name, page_number,
               section, locator, quote, fetched_at, created_at
        FROM field_evidence_v2
        """
    )

    connection.execute("DROP TABLE field_evidence_v2")
    connection.execute("DROP TABLE attachments_v2")
    connection.execute("DROP TABLE collection_run_publications_v2")
    connection.execute("DROP TABLE source_publications_v2")
    connection.execute(
        "CREATE INDEX idx_publications_event ON source_publications(notice_event_id, published_at)"
    )
    connection.execute(
        "CREATE INDEX idx_attachments_publication ON attachments(publication_id)"
    )
    connection.execute(
        "CREATE INDEX idx_evidence_publication_field ON field_evidence(publication_id, field_path)"
    )


def create_contract_history(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE publication_payload_versions (
            payload_version_id TEXT PRIMARY KEY,
            publication_id TEXT NOT NULL,
            version INTEGER NOT NULL CHECK(version >= 1),
            payload_fingerprint TEXT NOT NULL,
            notice_json TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            CHECK(length(payload_fingerprint) = 64),
            CHECK(payload_fingerprint NOT GLOB '*[^0-9a-f]*'),
            UNIQUE(publication_id, version),
            UNIQUE(publication_id, payload_fingerprint),
            FOREIGN KEY(publication_id) REFERENCES source_publications(publication_id) ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE attachment_versions (
            attachment_version_id TEXT PRIMARY KEY,
            attachment_pk TEXT NOT NULL,
            version INTEGER NOT NULL CHECK(version >= 1),
            state_fingerprint TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('discovered', 'download_allowed', 'downloaded', 'blocked', 'restricted', 'invalid', 'failed')),
            media_type TEXT,
            size_bytes INTEGER CHECK(size_bytes IS NULL OR size_bytes >= 0),
            content_sha256 TEXT,
            fetched_at TEXT,
            failure_reason TEXT,
            recorded_at TEXT NOT NULL,
            CHECK(length(state_fingerprint) = 64),
            CHECK(state_fingerprint NOT GLOB '*[^0-9a-f]*'),
            CHECK(content_sha256 IS NULL OR (length(content_sha256) = 64 AND content_sha256 NOT GLOB '*[^0-9a-f]*')),
            UNIQUE(attachment_pk, version),
            UNIQUE(attachment_pk, state_fingerprint),
            FOREIGN KEY(attachment_pk) REFERENCES attachments(attachment_pk) ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        "CREATE INDEX idx_payload_versions_publication ON publication_payload_versions(publication_id, version)"
    )
    connection.execute(
        "CREATE INDEX idx_attachment_versions_attachment ON attachment_versions(attachment_pk, version)"
    )


def _create_task_identities(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE task_identities (
            task_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
        """
    )
    for table in ("tasks", "project_snapshot_versions", "source_watermark_versions", "collection_runs"):
        connection.execute(
            f"""
            INSERT OR IGNORE INTO task_identities(task_id, created_at)
            SELECT DISTINCT source.task_id, COALESCE(
                (SELECT MIN(created_at) FROM tasks WHERE tasks.task_id = source.task_id),
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            )
            FROM {table} AS source
            """
        )


def _rebuild_task_scoped_history(connection: sqlite3.Connection) -> None:
    connection.execute(
        "ALTER TABLE project_snapshot_versions RENAME TO project_snapshot_versions_v3"
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
            FOREIGN KEY(task_id) REFERENCES task_identities(task_id) ON DELETE RESTRICT,
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
        FROM project_snapshot_versions_v3
        """
    )
    connection.execute("DROP TABLE project_snapshot_versions_v3")
    connection.execute(
        "CREATE INDEX idx_snapshot_versions_task_project ON project_snapshot_versions(task_id, project_id, version)"
    )

    connection.execute(
        "ALTER TABLE source_watermark_versions RENAME TO source_watermark_versions_v3"
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
            FOREIGN KEY(task_id) REFERENCES task_identities(task_id) ON DELETE RESTRICT,
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
        FROM source_watermark_versions_v3
        """
    )
    connection.execute("DROP TABLE source_watermark_versions_v3")
    connection.execute(
        "CREATE INDEX idx_watermark_versions_task_source ON source_watermark_versions(task_id, source_id, created_at)"
    )
