"""Use the complete DATA_CONTRACT source-publication identity tuple."""

from __future__ import annotations

import sqlite3

from .v0004_contract_history import (
    create_contract_history,
    rebuild_source_publication_graph,
)


CHECKSUM = "0205f6e3dac90ce1ebd8baaec6da44a765ba45db7a626616ce0f77136e39380e"


def upgrade(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TEMP TABLE publication_payload_versions_v4_backup AS
        SELECT * FROM publication_payload_versions
        """
    )
    connection.execute(
        """
        CREATE TEMP TABLE attachment_versions_v4_backup AS
        SELECT * FROM attachment_versions
        """
    )
    # Drop the dependent history tables before SQLite renames the parent. If
    # they remained present, their foreign keys would follow the renamed v4
    # parent tables and prevent the graph rebuild from dropping those parents.
    connection.execute("DROP TABLE publication_payload_versions")
    connection.execute("DROP TABLE attachment_versions")
    rebuild_source_publication_graph(connection, identity_version=5)
    create_contract_history(connection)
    connection.execute(
        """
        INSERT INTO publication_payload_versions(
            payload_version_id, publication_id, version,
            payload_fingerprint, notice_json, recorded_at
        )
        SELECT payload_version_id, publication_id, version,
               payload_fingerprint, notice_json, recorded_at
        FROM publication_payload_versions_v4_backup
        """
    )
    connection.execute(
        """
        INSERT INTO attachment_versions(
            attachment_version_id, attachment_pk, version,
            state_fingerprint, status, media_type, size_bytes,
            content_sha256, fetched_at, failure_reason, recorded_at
        )
        SELECT attachment_version_id, attachment_pk, version,
               state_fingerprint, status, media_type, size_bytes,
               content_sha256, fetched_at, failure_reason, recorded_at
        FROM attachment_versions_v4_backup
        """
    )
    connection.execute("DROP TABLE publication_payload_versions_v4_backup")
    connection.execute("DROP TABLE attachment_versions_v4_backup")
