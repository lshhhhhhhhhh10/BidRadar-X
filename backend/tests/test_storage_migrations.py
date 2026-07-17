from __future__ import annotations

from datetime import datetime
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.schemas.tender import (
    Attachment,
    EvidenceReference,
    RequirementFact,
    RequirementSection,
    SourceRecord,
    TenderNotice,
)
from app.storage import database as database_module
from app.storage.database import MIGRATIONS, Migration, apply_migrations
from app.storage.models import AttachmentState, SourceResponseMetadata, SourceWatermark
from app.storage.repository import Repository


def make_notice(
    *,
    source_id: str = "source-a",
    notice_id: str = "notice-001",
    source_url: str = "https://source-a.example/notices/001",
    attachment_id: str = "attachment-001",
    attachment_url: str = "https://source-a.example/files/001.pdf",
    project_fingerprint: str = "1" * 64,
    notice_fingerprint: str = "2" * 64,
    raw_fingerprint: str = "3" * 64,
    publication_role: str = "original",
) -> TenderNotice:
    fetched_at = "2026-07-14T09:05:00+08:00"
    return TenderNotice(
        notice_id=notice_id,
        notice_type="tender",
        project_code=None,
        title="通用设备采购公告",
        published_at="2026-07-14T09:00:00+08:00",
        source=SourceRecord(
            source_id=source_id,
            source_name=f"公开来源 {source_id}",
            source_url=source_url,
            publication_role=publication_role,
            canonical_notice_url=(
                "https://source-a.example/notices/001"
                if publication_role == "republication"
                else None
            ),
            source_notice_id="source-notice-001",
        ),
        core_content="采购通用计算设备，具体参数以附件为准。",
        attachments=[
            Attachment(
                attachment_id=attachment_id,
                name="采购需求.pdf",
                url=attachment_url,
            )
        ],
        purchaser="示例采购单位",
        budget="1000000.00",
        raw_content_fingerprint=raw_fingerprint,
        notice_stable_fingerprint=notice_fingerprint,
        project_stable_fingerprint=project_fingerprint,
        fetched_at=fetched_at,
        evidence=[
            EvidenceReference(
                evidence_id="evidence-001",
                field_path="core_content",
                source_url=attachment_url,
                attachment_id=attachment_id,
                document_name="采购需求.pdf",
                page_number=3,
                section="技术参数",
                locator="pdf:p3",
                quote="采购通用计算设备。",
                fetched_at=fetched_at,
            ),
            EvidenceReference(
                evidence_id="evidence-purchaser",
                field_path="purchaser",
                source_url=source_url,
                locator="公告概要/采购人",
                quote="采购人：示例采购单位",
                fetched_at=fetched_at,
            ),
            EvidenceReference(
                evidence_id="evidence-budget",
                field_path="budget",
                source_url=source_url,
                locator="公告概要/预算",
                quote="预算金额：1000000.00元",
                fetched_at=fetched_at,
            ),
        ],
        requirement_sections=[
            RequirementSection(
                section_id="technical",
                title="技术与服务要求",
                facts=[
                    RequirementFact(
                        label="兼容性要求",
                        value=None,
                        unknown_reason="公告未披露",
                    )
                ],
            )
        ],
    )


class StorageTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database_path = self.root / "app.db"
        self.patches = [
            patch.object(database_module, "DATA_DIR", self.root),
            patch.object(database_module, "DATABASE_PATH", self.database_path),
        ]
        for active_patch in self.patches:
            active_patch.start()

    def tearDown(self) -> None:
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temporary_directory.cleanup()


class StorageMigrationTest(StorageTestCase):
    def test_empty_database_upgrade_and_repeat_are_versioned_and_idempotent(self) -> None:
        database_module.initialize_database()
        database_module.initialize_database()

        with database_module.connect() as connection:
            versions = connection.execute(
                "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
            snapshot_foreign_tables = {
                row["table"]
                for row in connection.execute(
                    "PRAGMA foreign_key_list(project_snapshot_versions)"
                )
            }
            watermark_foreign_tables = {
                row["table"]
                for row in connection.execute(
                    "PRAGMA foreign_key_list(source_watermark_versions)"
                )
            }

        self.assertEqual([row["version"] for row in versions], [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertTrue(all(row["checksum"] for row in versions))
        self.assertTrue(
            {
                "projects",
                "notice_events",
                "source_publications",
                "attachments",
                "collection_runs",
                "field_evidence",
                "project_snapshot_versions",
                "source_watermark_versions",
                "delivery_events",
                "run_versions",
                "task_identities",
                "publication_payload_versions",
                "attachment_versions",
                "spend_policy",
                "spend_events",
            }.issubset(tables)
        )
        self.assertEqual(foreign_key_errors, [])
        self.assertIn("task_identities", snapshot_foreign_tables)
        self.assertIn("task_identities", watermark_foreign_tables)

    def test_existing_prototype_database_is_upgraded_without_losing_rows(self) -> None:
        with database_module.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE project_snapshots (
                    task_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    facts_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (task_id, project_id)
                );
                CREATE TABLE source_watermarks (
                    task_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    watermark_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (task_id, source_id)
                );
                INSERT INTO project_snapshots(task_id, project_id, facts_json, updated_at)
                VALUES ('legacy-task', 'legacy-project', '{"budget":"42"}', '2026-07-13T00:00:00+08:00');
                INSERT INTO source_watermarks(task_id, source_id, watermark_json, updated_at)
                VALUES ('legacy-task', 'legacy-source', '{"record_count":1}', '2026-07-13T00:00:00+08:00');
                """
            )

        database_module.initialize_database()
        database_module.initialize_database()

        with database_module.connect() as connection:
            snapshot = connection.execute(
                "SELECT * FROM project_snapshots WHERE task_id = 'legacy-task'"
            ).fetchone()
            watermark = connection.execute(
                "SELECT * FROM source_watermarks WHERE task_id = 'legacy-task'"
            ).fetchone()
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(project_snapshots)")
            }
            versions = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()

        self.assertEqual(snapshot["facts_json"], '{"budget":"42"}')
        self.assertEqual(watermark["watermark_json"], '{"record_count":1}')
        self.assertTrue(
            {"project_stable_fingerprint", "snapshot_fingerprint", "snapshot_json", "version"}
            .issubset(columns)
        )
        self.assertEqual([row["version"] for row in versions], [1, 2, 3, 4, 5, 6, 7, 8])

    def test_populated_v4_database_upgrades_to_v5_without_losing_history(self) -> None:
        original_apply_migrations = database_module.apply_migrations

        def apply_through_v4(connection: sqlite3.Connection) -> None:
            original_apply_migrations(connection, MIGRATIONS[:4])

        with patch.object(
            database_module,
            "apply_migrations",
            side_effect=apply_through_v4,
        ):
            repository = Repository()
            repository.create_task("task-001", "equipment procurement notices", "daily")
            repository.start_collection_run(
                collection_run_id="collection-run-v4",
                task_id="task-001",
                source_id="source-a",
                idempotency_key="collection-run-v4",
                started_at=datetime.fromisoformat("2026-07-14T09:00:00+08:00"),
            )
            repository.commit_collection_run(
                collection_run_id="collection-run-v4",
                notices=[make_notice()],
                watermark=SourceWatermark(
                    source_id="source-a",
                    published_at=datetime.fromisoformat("2026-07-14T09:00:00+08:00"),
                    source_notice_id="source-notice-001",
                ),
                attachment_states={
                    "attachment-001": AttachmentState(
                        status="downloaded",
                        media_type="application/pdf",
                        size_bytes=1024,
                        content_sha256="5" * 64,
                        fetched_at=datetime.fromisoformat(
                            "2026-07-14T09:05:30+08:00"
                        ),
                    )
                },
                completed_at=datetime.fromisoformat("2026-07-14T09:06:00+08:00"),
            )

        database_module.initialize_database()

        with database_module.connect() as connection:
            versions = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
            payload_count = connection.execute(
                "SELECT COUNT(*) FROM publication_payload_versions"
            ).fetchone()[0]
            attachment_version = connection.execute(
                "SELECT status, content_sha256 FROM attachment_versions"
            ).fetchone()
            foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()

        self.assertEqual([row["version"] for row in versions], [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(payload_count, 1)
        self.assertEqual(attachment_version["status"], "downloaded")
        self.assertEqual(attachment_version["content_sha256"], "5" * 64)
        self.assertEqual(foreign_key_errors, [])

    def test_changed_applied_migration_checksum_is_rejected(self) -> None:
        database_module.initialize_database()

        with database_module.connect() as connection:
            connection.execute(
                "UPDATE schema_migrations SET checksum = ? WHERE version = 5",
                ("b6da25bac11afee4ada4d1c7f2a96d1d2d66359b19ae4edb19c9f02651e153fd",),
            )

        with self.assertRaisesRegex(RuntimeError, "does not match its applied checksum"):
            database_module.initialize_database()

    def test_failed_migration_rolls_back_schema_and_does_not_advance_version(self) -> None:
        database_module.initialize_database()

        def fail_after_ddl(connection: sqlite3.Connection) -> None:
            connection.execute("CREATE TABLE half_migrated(value TEXT)")
            raise RuntimeError("injected migration failure")

        failing = Migration(MIGRATIONS[-1].version + 1, "injected_failure", "test-checksum", fail_after_ddl)
        with database_module.connect() as connection:
            with self.assertRaisesRegex(RuntimeError, "injected migration failure"):
                apply_migrations(connection, (*MIGRATIONS, failing))

        with database_module.connect() as connection:
            versions = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
            half_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'half_migrated'"
            ).fetchone()
            connection.execute(
                "INSERT INTO tasks(task_id, query, frequency, created_at) VALUES (?, ?, ?, ?)",
                ("still-usable", "旧库仍可用", "once", "2026-07-14T10:00:00+08:00"),
            )

        self.assertEqual([row["version"] for row in versions], [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertIsNone(half_table)

    def test_v8_backfills_tombstones_for_previously_deleted_duplicate_runs(self) -> None:
        original_apply_migrations = database_module.apply_migrations

        def apply_through_v7(connection: sqlite3.Connection) -> None:
            original_apply_migrations(connection, MIGRATIONS[:7])

        with patch.object(
            database_module,
            "apply_migrations",
            side_effect=apply_through_v7,
        ):
            repository = Repository()
            repository.create_task("history-backfill", "查询服务器采购公告", "once")
            state = {
                "task_id": "history-backfill",
                "status": "completed",
                "query": "查询服务器采购公告",
                "frequency": "once",
                "projects": [],
            }
            repository.save_run({**state, "run_id": "history-backfill-a"})
            repository.save_run(
                {
                    **state,
                    "run_id": "history-backfill-b",
                    "frequency": "weekly",
                }
            )
            with database_module.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO hidden_report_runs(run_id, hidden_at)
                    VALUES (?, ?)
                    """,
                    ("history-backfill-a", "2026-07-17T23:51:00+08:00"),
                )

        database_module.initialize_database()

        with database_module.connect() as connection:
            hidden = connection.execute(
                "SELECT run_id FROM hidden_report_runs ORDER BY run_id"
            ).fetchall()

        self.assertEqual(
            [row["run_id"] for row in hidden],
            ["history-backfill-a", "history-backfill-b"],
        )


class ProvenancePersistenceTest(StorageTestCase):
    def _start_run(self, repository: Repository, run_id: str = "collection-run-001") -> None:
        repository.create_task("task-001", "查询设备采购公告", "daily")
        repository.start_collection_run(
            collection_run_id=run_id,
            task_id="task-001",
            source_id="source-a",
            idempotency_key=run_id,
            started_at=datetime.fromisoformat("2026-07-14T09:00:00+08:00"),
        )

    def test_three_identity_layers_attachments_evidence_and_unknowns_round_trip(self) -> None:
        repository = Repository()
        self._start_run(repository)
        original = make_notice()
        republication = make_notice(
            source_id="source-b",
            notice_id="repost-001",
            source_url="https://source-b.example/reposts/001",
            attachment_id="attachment-repost-001",
            attachment_url="https://source-b.example/files/001.pdf",
            raw_fingerprint="4" * 64,
            publication_role="republication",
        )
        watermark = SourceWatermark(
            source_id="source-a",
            published_at=datetime.fromisoformat("2026-07-14T09:00:00+08:00"),
            source_notice_id="source-notice-001",
            source_url="https://source-a.example/notices/001",
        )
        repository.commit_collection_run(
            collection_run_id="collection-run-001",
            notices=[original, republication],
            watermark=watermark,
            attachment_states={
                "attachment-001": AttachmentState(
                    status="downloaded",
                    media_type="application/pdf",
                    size_bytes=1024,
                    content_sha256="5" * 64,
                    fetched_at=datetime.fromisoformat("2026-07-14T09:05:30+08:00"),
                ),
                "attachment-repost-001": AttachmentState(
                    status="failed",
                    failure_reason="远端入口暂不可用",
                ),
            },
            response_metadata=SourceResponseMetadata(
                http_status=200,
                content_type="text/html; charset=utf-8",
                etag=None,
                last_modified=None,
                metadata={"cache_status": "miss"},
            ),
            completed_at=datetime.fromisoformat("2026-07-14T09:06:00+08:00"),
        )
        reused_run = repository.start_collection_run(
            collection_run_id="collection-run-duplicate",
            task_id="task-001",
            source_id="source-a",
            idempotency_key="collection-run-001",
            started_at=datetime.fromisoformat("2026-07-14T09:07:00+08:00"),
        )
        repository.commit_collection_run(
            collection_run_id="collection-run-001",
            notices=[original, republication],
            watermark=watermark,
            completed_at=datetime.fromisoformat("2026-07-14T09:08:00+08:00"),
        )

        with database_module.connect() as connection:
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "projects",
                    "notice_events",
                    "source_publications",
                    "attachments",
                    "field_evidence",
                    "collection_runs",
                    "collection_run_publications",
                    "source_watermark_versions",
                    "publication_payload_versions",
                    "attachment_versions",
                )
            }
            publications = connection.execute(
                "SELECT * FROM source_publications ORDER BY source_id"
            ).fetchall()
            attachments = connection.execute(
                "SELECT * FROM attachments ORDER BY attachment_id"
            ).fetchall()
            evidence = connection.execute("SELECT * FROM field_evidence").fetchone()
            watermark_row = connection.execute(
                "SELECT * FROM source_watermark_versions"
            ).fetchone()

        self.assertEqual(counts["projects"], 1)
        self.assertEqual(counts["notice_events"], 1)
        self.assertEqual(counts["source_publications"], 2)
        self.assertEqual(counts["attachments"], 2)
        self.assertEqual(counts["field_evidence"], 6)
        self.assertEqual(counts["collection_runs"], 1)
        self.assertEqual(counts["collection_run_publications"], 2)
        self.assertEqual(counts["source_watermark_versions"], 1)
        self.assertEqual(counts["publication_payload_versions"], 2)
        self.assertEqual(counts["attachment_versions"], 2)
        self.assertEqual(reused_run["collection_run_id"], "collection-run-001")
        self.assertEqual(
            [row["publication_role"] for row in publications],
            ["original", "republication"],
        )
        self.assertEqual(publications[0]["published_at"], "2026-07-14T09:00:00+08:00")
        self.assertIsNone(publications[0]["response_etag"])
        self.assertEqual(attachments[0]["status"], "downloaded")
        self.assertEqual(attachments[0]["media_type"], "application/pdf")
        self.assertEqual(attachments[0]["size_bytes"], 1024)
        self.assertEqual(attachments[0]["content_sha256"], "5" * 64)
        self.assertEqual(attachments[0]["fetched_at"], "2026-07-14T09:05:30+08:00")
        self.assertIsNone(attachments[1]["size_bytes"])
        self.assertIsNone(attachments[1]["content_sha256"])
        self.assertIsNone(attachments[1]["fetched_at"])
        self.assertEqual(attachments[1]["failure_reason"], "远端入口暂不可用")
        self.assertEqual(evidence["page_number"], 3)
        self.assertEqual(evidence["locator"], "pdf:p3")
        self.assertEqual(evidence["fetched_at"], "2026-07-14T09:05:00+08:00")
        self.assertEqual(watermark_row["cursor_source_notice_id"], "source-notice-001")
        self.assertEqual(
            watermark_row["cursor_source_url"],
            "https://source-a.example/notices/001",
        )
        loaded = repository.get_tender_notice(publications[0]["publication_id"])
        self.assertEqual(loaded.purchaser, "示例采购单位")
        self.assertEqual(str(loaded.budget), "1000000.00")
        self.assertEqual(loaded.requirement_sections[0].section_id, "technical")
        self.assertEqual(
            loaded.requirement_sections[0].facts[0].unknown_reason,
            "公告未披露",
        )

    def test_foreign_keys_unique_constraints_and_attachment_evidence_scope_are_enforced(self) -> None:
        repository = Repository()
        self._start_run(repository)
        repository.commit_collection_run(
            collection_run_id="collection-run-001",
            notices=[make_notice()],
            watermark=SourceWatermark(
                source_id="source-a",
                published_at=datetime.fromisoformat("2026-07-14T09:00:00+08:00"),
                source_notice_id="source-notice-001",
            ),
            completed_at=datetime.fromisoformat("2026-07-14T09:06:00+08:00"),
        )

        with database_module.connect() as connection:
            publication = connection.execute("SELECT * FROM source_publications").fetchone()
            attachment = connection.execute("SELECT * FROM attachments").fetchone()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE field_evidence SET attachment_id = 'missing-attachment'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO source_publications(
                        publication_id, notice_id, notice_event_id, source_id, source_name,
                        source_url, publication_role, title, published_at, fetched_at,
                        core_content, raw_content_fingerprint, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "9" * 64,
                        publication["notice_id"],
                        publication["notice_event_id"],
                        publication["source_id"],
                        publication["source_name"],
                        publication["source_url"],
                        publication["publication_role"],
                        publication["title"],
                        publication["published_at"],
                        publication["fetched_at"],
                        publication["core_content"],
                        publication["raw_content_fingerprint"],
                        publication["created_at"],
                    ),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM source_publications WHERE publication_id = ?",
                    (attachment["publication_id"],),
                )

    def test_publication_role_is_part_of_the_stable_source_record_identity(self) -> None:
        repository = Repository()
        self._start_run(repository)
        repository.commit_collection_run(
            collection_run_id="collection-run-001",
            notices=[
                make_notice(publication_role="original"),
                make_notice(publication_role="republication"),
            ],
            watermark=SourceWatermark(
                source_id="source-a",
                published_at=datetime.fromisoformat("2026-07-14T09:00:00+08:00"),
                source_notice_id="source-notice-001",
            ),
            completed_at=datetime.fromisoformat("2026-07-14T09:06:00+08:00"),
        )

        with database_module.connect() as connection:
            publications = connection.execute(
                "SELECT publication_id, publication_role FROM source_publications ORDER BY publication_role"
            ).fetchall()

        self.assertEqual(len(publications), 2)
        self.assertNotEqual(publications[0]["publication_id"], publications[1]["publication_id"])
        self.assertEqual(
            {row["publication_role"] for row in publications},
            {"original", "republication"},
        )

    def test_attachment_state_changes_append_history_and_update_the_current_view(self) -> None:
        repository = Repository()
        self._start_run(repository)
        watermark = SourceWatermark(
            source_id="source-a",
            published_at=datetime.fromisoformat("2026-07-14T09:00:00+08:00"),
            source_notice_id="source-notice-001",
        )
        repository.commit_collection_run(
            collection_run_id="collection-run-001",
            notices=[make_notice()],
            watermark=watermark,
            completed_at=datetime.fromisoformat("2026-07-14T09:06:00+08:00"),
        )
        repository.start_collection_run(
            collection_run_id="collection-run-002",
            task_id="task-001",
            source_id="source-a",
            idempotency_key="collection-run-002",
            started_at=datetime.fromisoformat("2026-07-14T10:00:00+08:00"),
        )
        repository.commit_collection_run(
            collection_run_id="collection-run-002",
            notices=[make_notice()],
            watermark=watermark,
            attachment_states={
                "attachment-001": AttachmentState(
                    status="downloaded",
                    media_type="application/pdf",
                    size_bytes=2048,
                    content_sha256="6" * 64,
                    fetched_at=datetime.fromisoformat("2026-07-14T10:01:00+08:00"),
                )
            },
            completed_at=datetime.fromisoformat("2026-07-14T10:02:00+08:00"),
        )
        repository.start_collection_run(
            collection_run_id="collection-run-003",
            task_id="task-001",
            source_id="source-a",
            idempotency_key="collection-run-003",
            started_at=datetime.fromisoformat("2026-07-14T11:00:00+08:00"),
        )
        repository.commit_collection_run(
            collection_run_id="collection-run-003",
            notices=[make_notice()],
            watermark=watermark,
            completed_at=datetime.fromisoformat("2026-07-14T11:01:00+08:00"),
        )

        with database_module.connect() as connection:
            current = connection.execute("SELECT * FROM attachments").fetchone()
            versions = connection.execute(
                "SELECT status FROM attachment_versions ORDER BY version"
            ).fetchall()

        self.assertEqual([row["status"] for row in versions], ["discovered", "downloaded"])
        self.assertEqual(current["status"], "downloaded")
        self.assertEqual(current["size_bytes"], 2048)
        self.assertEqual(current["content_sha256"], "6" * 64)

    def test_same_source_identity_fields_can_keep_distinct_publication_urls(self) -> None:
        repository = Repository()
        self._start_run(repository)
        repository.commit_collection_run(
            collection_run_id="collection-run-001",
            notices=[
                make_notice(),
                make_notice(
                    source_url="https://source-a.example/archive/notices/001",
                    attachment_id="attachment-archive-001",
                    attachment_url="https://source-a.example/archive/files/001.pdf",
                ),
            ],
            watermark=SourceWatermark(
                source_id="source-a",
                published_at=datetime.fromisoformat("2026-07-14T09:00:00+08:00"),
                source_notice_id="source-notice-001",
            ),
            completed_at=datetime.fromisoformat("2026-07-14T09:06:00+08:00"),
        )

        with database_module.connect() as connection:
            publications = connection.execute(
                "SELECT publication_id, source_url FROM source_publications ORDER BY source_url"
            ).fetchall()

        self.assertEqual(len(publications), 2)
        self.assertNotEqual(publications[0]["publication_id"], publications[1]["publication_id"])

    def test_same_url_role_and_raw_content_keep_distinct_notice_ids(self) -> None:
        repository = Repository()
        self._start_run(repository)
        repository.commit_collection_run(
            collection_run_id="collection-run-001",
            notices=[
                make_notice(),
                make_notice(
                    notice_id="notice-002",
                    attachment_id="attachment-002",
                    attachment_url="https://source-a.example/files/002.pdf",
                ),
            ],
            watermark=SourceWatermark(
                source_id="source-a",
                published_at=datetime.fromisoformat("2026-07-14T09:00:00+08:00"),
                source_notice_id="source-notice-001",
            ),
            completed_at=datetime.fromisoformat("2026-07-14T09:06:00+08:00"),
        )

        with database_module.connect() as connection:
            publications = connection.execute(
                "SELECT publication_id, notice_id FROM source_publications ORDER BY notice_id"
            ).fetchall()

        self.assertEqual([row["notice_id"] for row in publications], ["notice-001", "notice-002"])
        self.assertNotEqual(publications[0]["publication_id"], publications[1]["publication_id"])

    def test_failed_collection_transaction_keeps_run_and_watermark_at_old_state(self) -> None:
        repository = Repository()
        self._start_run(repository)
        conflicting_notice = make_notice(
            source_id="source-b",
            notice_id="conflicting-notice",
            source_url="https://source-b.example/notices/conflict",
            attachment_id="attachment-conflict",
            attachment_url="https://source-b.example/files/conflict.pdf",
            project_fingerprint="8" * 64,
            raw_fingerprint="7" * 64,
            publication_role="republication",
        )

        with self.assertRaisesRegex(ValueError, "notice identity"):
            repository.commit_collection_run(
                collection_run_id="collection-run-001",
                notices=[make_notice(), conflicting_notice],
                watermark=SourceWatermark(
                    source_id="source-a",
                    published_at=datetime.fromisoformat("2026-07-14T09:00:00+08:00"),
                    source_notice_id="source-notice-001",
                ),
                completed_at=datetime.fromisoformat("2026-07-14T09:06:00+08:00"),
            )

        with database_module.connect() as connection:
            run = connection.execute("SELECT * FROM collection_runs").fetchone()
            project_count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            publication_count = connection.execute(
                "SELECT COUNT(*) FROM source_publications"
            ).fetchone()[0]
            watermark_count = connection.execute(
                "SELECT COUNT(*) FROM source_watermarks"
            ).fetchone()[0]
            watermark_version_count = connection.execute(
                "SELECT COUNT(*) FROM source_watermark_versions"
            ).fetchone()[0]

        self.assertEqual(run["status"], "running")
        self.assertEqual(project_count, 0)
        self.assertEqual(publication_count, 0)
        self.assertEqual(watermark_count, 0)
        self.assertEqual(watermark_version_count, 0)

    def test_snapshot_run_delivery_and_change_history_are_idempotent_and_auditable(self) -> None:
        repository = Repository()
        repository.create_task("task-001", "查询设备采购公告", "daily")
        first_run = {
            "run_id": "workflow-run-001",
            "task_id": "task-001",
            "status": "running",
        }
        repository.save_run(first_run)
        repository.save_run(first_run)
        repository.save_run({**first_run, "status": "completed"})

        def snapshot(fingerprint: str, budget: str) -> dict:
            return {
                "project_id": "project-1111111111111111",
                "project_stable_fingerprint": "1" * 64,
                "snapshot_fingerprint": fingerprint,
                "facts": {"budget": budget},
                "normalized_facts": {"budget": budget},
                "lifecycle": [],
                "notices": [],
            }

        for index, item in enumerate(
            (snapshot("a" * 64, "42"), snapshot("b" * 64, "43")),
            start=1,
        ):
            delivery_fingerprint = str(index) * 64
            acquired, _ = repository.reserve_delivery(
                task_id="task-001",
                run_id=f"delivery-run-{index}",
                delivery_type="material_change" if index == 2 else "full_snapshot",
                delivery_fingerprint=delivery_fingerprint,
                changes=[] if index == 1 else [{"field_path": "budget", "current_value": "43"}],
            )
            self.assertTrue(acquired)
            repository.commit_generated_delivery(
                task_id="task-001",
                run_id=f"delivery-run-{index}",
                delivery_fingerprint=delivery_fingerprint,
                artifact_uri=f"report-{index}.docx",
                snapshots=[item],
                watermarks=[],
            )

        with database_module.connect() as connection:
            run_versions = connection.execute(
                "SELECT status FROM run_versions ORDER BY version"
            ).fetchall()
            snapshot_versions = connection.execute(
                "SELECT version FROM project_snapshot_versions ORDER BY version"
            ).fetchall()
            delivery_events = connection.execute(
                "SELECT status FROM delivery_events ORDER BY created_at, event_id"
            ).fetchall()
            change_versions = connection.execute(
                "SELECT COUNT(*) FROM delivery_change_versions"
            ).fetchone()[0]

        self.assertEqual([row["status"] for row in run_versions], ["running", "completed"])
        self.assertEqual([row["version"] for row in snapshot_versions], [1, 2])
        self.assertEqual(
            [row["status"] for row in delivery_events],
            ["pending", "generated", "pending", "generated"],
        )
        self.assertEqual(change_versions, 2)


if __name__ == "__main__":
    unittest.main()
