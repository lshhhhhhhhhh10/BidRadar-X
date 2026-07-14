from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import sqlite3
import tempfile
from threading import Lock
from typing import Callable, Iterable

from .migrations import MIGRATION_SPECS


# The bundled Python runtime cannot reliably open SQLite files below a Windows
# path containing non-ASCII characters. Keep simulation data in the user's
# local temp area by default and allow an explicit ASCII path override.
DATA_DIR = Path(
    os.environ.get(
        "TENDER_DATA_DIR",
        Path(tempfile.gettempdir()) / "TenderIntelligence",
    )
)
DATABASE_PATH = DATA_DIR / "app.db"
_INITIALIZE_LOCK = Lock()


class ClosingConnection(sqlite3.Connection):
    """Commit or roll back like sqlite3, then release Windows file handles."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


@dataclass(frozen=True)
class Migration:
    """One immutable, ordered database schema migration."""

    version: int
    name: str
    checksum: str
    upgrade: Callable[[sqlite3.Connection], None]


MIGRATIONS = tuple(Migration(*spec) for spec in MIGRATION_SPECS)


def connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=5,
        factory=ClosingConnection,
    )
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection
    except Exception:
        connection.close()
        raise


def initialize_database() -> None:
    """Upgrade the configured database to the latest committed schema."""

    with _INITIALIZE_LOCK:
        with connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            apply_migrations(connection)


def apply_migrations(
    connection: sqlite3.Connection,
    migrations: Iterable[Migration] = MIGRATIONS,
) -> None:
    """Apply pending migrations one at a time with atomic version recording."""

    ordered = tuple(migrations)
    versions = [migration.version for migration in ordered]
    if versions != sorted(versions) or len(versions) != len(set(versions)):
        raise ValueError("migrations must have unique versions in ascending order")

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    applied = {
        row["version"]: row
        for row in connection.execute(
            "SELECT version, name, checksum FROM schema_migrations"
        ).fetchall()
    }
    unknown_versions = sorted(set(applied).difference(versions))
    if unknown_versions:
        raise RuntimeError(
            f"database has migrations newer than this application: {unknown_versions}"
        )
    applied_versions = sorted(applied)
    if applied_versions != versions[: len(applied_versions)]:
        raise RuntimeError("database migration history is not a contiguous prefix")

    for migration in ordered:
        existing = applied.get(migration.version)
        if existing is not None:
            if (
                existing["name"] != migration.name
                or existing["checksum"] != migration.checksum
            ):
                raise RuntimeError(
                    f"migration {migration.version} does not match its applied checksum"
                )
            continue

        try:
            connection.execute("BEGIN IMMEDIATE")
            migration.upgrade(connection)
            connection.execute(
                """
                INSERT INTO schema_migrations(version, name, checksum, applied_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    migration.version,
                    migration.name,
                    migration.checksum,
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
