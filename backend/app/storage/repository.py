from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Mapping
from uuid import uuid4

from ..schemas.tender import TenderNotice
from .database import connect, initialize_database
from .models import (
    AttachmentState,
    SourceResponseMetadata,
    SourceWatermark,
    WatermarkCursor,
)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _audit_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _aware_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.isoformat(timespec="seconds")


def _stable_id(*parts: str) -> str:
    return sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_fingerprint(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class Repository:
    pending_stale_after = timedelta(minutes=5)

    def __init__(self) -> None:
        initialize_database()

    def create_task(self, task_id: str, query: str, frequency: str) -> None:
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks(task_id, query, frequency, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    query = excluded.query,
                    frequency = excluded.frequency
                """,
                (task_id, query, frequency, _now()),
            )
            self._ensure_task_identity(connection, task_id, _now())

    def save_run(self, state: dict[str, Any]) -> None:
        canonical = _canonical_json(state)
        result_fingerprint = _json_fingerprint(state)
        now = _now()
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO runs(run_id, task_id, status, result_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    task_id = excluded.task_id,
                    status = excluded.status,
                    result_json = excluded.result_json
                """,
                (
                    state["run_id"],
                    state["task_id"],
                    state["status"],
                    canonical,
                    now,
                ),
            )
            existing = connection.execute(
                """
                SELECT 1 FROM run_versions
                WHERE run_id = ? AND result_fingerprint = ?
                """,
                (state["run_id"], result_fingerprint),
            ).fetchone()
            if existing is None:
                version = connection.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 FROM run_versions WHERE run_id = ?",
                    (state["run_id"],),
                ).fetchone()[0]
                connection.execute(
                    """
                    INSERT INTO run_versions(
                        run_version_id, run_id, version, status,
                        result_fingerprint, result_json, recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _stable_id(state["run_id"], result_fingerprint),
                        state["run_id"],
                        version,
                        state["status"],
                        result_fingerprint,
                        canonical,
                        _audit_now(),
                    ),
                )

    def load_snapshots(self, task_id: str) -> dict[str, dict[str, Any]]:
        with connect() as connection:
            rows = connection.execute(
                "SELECT project_id, facts_json FROM project_snapshots WHERE task_id = ?",
                (task_id,),
            ).fetchall()
        return {row["project_id"]: json.loads(row["facts_json"]) for row in rows}

    def load_project_snapshots(self, task_id: str) -> dict[str, dict[str, Any]]:
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT project_id, project_stable_fingerprint, facts_json,
                       snapshot_json, snapshot_fingerprint, version, updated_at
                FROM project_snapshots
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchall()
        snapshots: dict[str, dict[str, Any]] = {}
        for row in rows:
            snapshot = (
                json.loads(row["snapshot_json"])
                if row["snapshot_json"]
                else {
                    "project_id": row["project_id"],
                    "project_stable_fingerprint": row["project_stable_fingerprint"] or row["project_id"],
                    "facts": json.loads(row["facts_json"]),
                    "normalized_facts": json.loads(row["facts_json"]),
                    "lifecycle": [],
                    "notices": [],
                }
            )
            snapshot["version"] = row["version"]
            snapshot["snapshot_fingerprint"] = row["snapshot_fingerprint"]
            snapshot["updated_at"] = row["updated_at"]
            key = row["project_stable_fingerprint"] or row["project_id"]
            snapshots[key] = snapshot
        return snapshots

    def save_snapshots(self, task_id: str, analyses: list[dict[str, Any]]) -> None:
        with connect() as connection:
            connection.executemany(
                """
                INSERT INTO project_snapshots(task_id, project_id, facts_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id, project_id)
                DO UPDATE SET facts_json = excluded.facts_json, updated_at = excluded.updated_at
                """,
                [
                    (task_id, item["project_id"], _canonical_json(item["facts"]), _now())
                    for item in analyses
                ],
            )

    def load_watermarks(self, task_id: str) -> dict[str, dict[str, Any]]:
        with connect() as connection:
            rows = connection.execute(
                "SELECT source_id, watermark_json FROM source_watermarks WHERE task_id = ?",
                (task_id,),
            ).fetchall()
        return {row["source_id"]: json.loads(row["watermark_json"]) for row in rows}

    def start_collection_run(
        self,
        *,
        collection_run_id: str,
        task_id: str,
        source_id: str,
        idempotency_key: str,
        started_at: datetime,
    ) -> dict[str, Any]:
        """Create or reuse an idempotent, source-scoped collection attempt."""

        started_at_text = _aware_timestamp(started_at)
        with connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO collection_runs(
                        collection_run_id, task_id, source_id, idempotency_key,
                        status, started_at, created_at
                    ) VALUES (?, ?, ?, ?, 'running', ?, ?)
                    """,
                    (
                        collection_run_id,
                        task_id,
                        source_id,
                        idempotency_key,
                        started_at_text,
                        _now(),
                    ),
                )
            except sqlite3.IntegrityError:
                row = connection.execute(
                    """
                    SELECT * FROM collection_runs
                    WHERE task_id = ? AND source_id = ? AND idempotency_key = ?
                    """,
                    (task_id, source_id, idempotency_key),
                ).fetchone()
                if row is None:
                    raise
                return dict(row)
            row = connection.execute(
                "SELECT * FROM collection_runs WHERE collection_run_id = ?",
                (collection_run_id,),
            ).fetchone()
        return dict(row)

    def commit_collection_run(
        self,
        *,
        collection_run_id: str,
        notices: list[TenderNotice],
        watermark: SourceWatermark,
        completed_at: datetime,
        attachment_states: Mapping[str, AttachmentState] | None = None,
        response_metadata: SourceResponseMetadata | None = None,
    ) -> None:
        """Atomically persist a successful collection batch and its watermark."""

        completed_at_text = _aware_timestamp(completed_at)
        states = attachment_states or {}
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT * FROM collection_runs WHERE collection_run_id = ?",
                (collection_run_id,),
            ).fetchone()
            if run is None:
                raise ValueError("collection run must be started before commit")
            if run["status"] == "succeeded":
                return
            if run["status"] != "running":
                raise ValueError(f"cannot commit collection run in {run['status']} state")
            if run["task_id"] is None:
                raise ValueError("collection run is missing its task identity")
            if watermark.source_id != run["source_id"]:
                raise ValueError("watermark source must match the collection run source")

            for notice in notices:
                self._persist_tender_notice(
                    connection,
                    notice,
                    collection_run_id=collection_run_id,
                    attachment_states=states,
                    response_metadata=response_metadata,
                )

            watermark_payload = {
                "task_id": run["task_id"],
                "source_id": watermark.source_id,
                "run_id": collection_run_id,
                "published_at": _aware_timestamp(watermark.published_at),
                "source_notice_id": watermark.source_notice_id,
                "source_url": watermark.source_url,
            }
            self._write_watermark(
                connection,
                task_id=run["task_id"],
                source_id=watermark.source_id,
                cursor=watermark.to_cursor(),
                collection_run_id=collection_run_id,
                watermark_payload=watermark_payload,
                now=completed_at_text,
            )
            connection.execute(
                """
                UPDATE collection_runs
                SET status = 'succeeded', completed_at = ?,
                    error_code = NULL, error_message = NULL
                WHERE collection_run_id = ? AND status = 'running'
                """,
                (completed_at_text, collection_run_id),
            )

    def fail_collection_run(
        self,
        *,
        collection_run_id: str,
        completed_at: datetime,
        error_code: str,
        error_message: str,
    ) -> bool:
        """Record a failed attempt without touching observations or watermarks."""

        with connect() as connection:
            return connection.execute(
                """
                UPDATE collection_runs
                SET status = 'failed', completed_at = ?, error_code = ?, error_message = ?
                WHERE collection_run_id = ? AND status = 'running'
                """,
                (
                    _aware_timestamp(completed_at),
                    error_code,
                    error_message[:2000],
                    collection_run_id,
                ),
            ).rowcount == 1

    def get_tender_notice(self, publication_id: str) -> TenderNotice | None:
        """Load the latest complete contract payload and validate it on read."""

        with connect() as connection:
            row = connection.execute(
                """
                SELECT notice_json
                FROM publication_payload_versions
                WHERE publication_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (publication_id,),
            ).fetchone()
        if row is None:
            return None
        return TenderNotice.model_validate(json.loads(row["notice_json"]))

    def list_deliveries(self, task_id: str) -> list[dict[str, Any]]:
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM deliveries
                WHERE task_id = ?
                ORDER BY created_at, delivery_id
                """,
                (task_id,),
            ).fetchall()
        return [self._delivery_row(row) for row in rows]

    def get_delivery(self, delivery_fingerprint: str) -> dict[str, Any] | None:
        with connect() as connection:
            row = connection.execute(
                "SELECT * FROM deliveries WHERE delivery_fingerprint = ?",
                (delivery_fingerprint,),
            ).fetchone()
        return self._delivery_row(row) if row is not None else None

    def latest_generated_delivery(self, task_id: str) -> dict[str, Any] | None:
        with connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM deliveries
                WHERE task_id = ? AND status IN ('generated', 'delivered')
                ORDER BY generated_at DESC, created_at DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        return self._delivery_row(row) if row is not None else None

    def reserve_delivery(
        self,
        *,
        task_id: str,
        run_id: str,
        delivery_type: str,
        delivery_fingerprint: str,
        changes: list[dict[str, Any]],
        project_stable_fingerprints: list[str] | None = None,
        notice_stable_fingerprints: list[str] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        now = _now()
        delivery_id = str(uuid4())
        with connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO deliveries(
                        delivery_id, task_id, run_id, delivery_type,
                        delivery_fingerprint, status, changes_json,
                        project_fingerprints_json, notice_fingerprints_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
                    """,
                    (
                        delivery_id,
                        task_id,
                        run_id,
                        delivery_type,
                        delivery_fingerprint,
                        _canonical_json(changes),
                        _canonical_json(sorted(project_stable_fingerprints or [])),
                        _canonical_json(sorted(notice_stable_fingerprints or [])),
                        now,
                        now,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM deliveries WHERE delivery_id = ?",
                    (delivery_id,),
                ).fetchone()
                self._record_delivery_changes(
                    connection,
                    delivery_id=delivery_id,
                    changes=changes,
                )
                self._record_delivery_event(
                    connection,
                    delivery_id=delivery_id,
                    run_id=run_id,
                    status="pending",
                )
                return True, self._delivery_row(row)
            except sqlite3.IntegrityError as error:
                row = connection.execute(
                    "SELECT * FROM deliveries WHERE delivery_fingerprint = ?",
                    (delivery_fingerprint,),
                ).fetchone()
                reclaimable = row is not None and (
                    row["status"] == "failed"
                    or (
                        row["status"] == "pending"
                        and datetime.fromisoformat(now) - datetime.fromisoformat(row["updated_at"])
                        > self.pending_stale_after
                    )
                )
                if reclaimable:
                    previous_status = row["status"]
                    previous_updated_at = row["updated_at"]
                    updated = connection.execute(
                        """
                        UPDATE deliveries
                        SET run_id = ?, status = 'pending', artifact_uri = NULL,
                            error = NULL, updated_at = ?, generated_at = NULL
                        WHERE delivery_fingerprint = ? AND status = ? AND updated_at = ?
                        """,
                        (
                            run_id,
                            now,
                            delivery_fingerprint,
                            previous_status,
                            previous_updated_at,
                        ),
                    ).rowcount
                    if updated:
                        row = connection.execute(
                            "SELECT * FROM deliveries WHERE delivery_fingerprint = ?",
                            (delivery_fingerprint,),
                        ).fetchone()
                        self._record_delivery_event(
                            connection,
                            delivery_id=row["delivery_id"],
                            run_id=run_id,
                            status="pending",
                        )
                        return True, self._delivery_row(row)
                if row is None:
                    raise RuntimeError("delivery reservation disappeared") from error
                return False, self._delivery_row(row)

    def mark_delivery_failed(
        self,
        delivery_fingerprint: str,
        run_id: str,
        error: str,
    ) -> None:
        with connect() as connection:
            updated = connection.execute(
                """
                UPDATE deliveries
                SET status = 'failed', error = ?, updated_at = ?
                WHERE delivery_fingerprint = ? AND run_id = ? AND status = 'pending'
                """,
                (error[:2000], _now(), delivery_fingerprint, run_id),
            ).rowcount
            if updated:
                row = connection.execute(
                    "SELECT delivery_id FROM deliveries WHERE delivery_fingerprint = ?",
                    (delivery_fingerprint,),
                ).fetchone()
                self._record_delivery_event(
                    connection,
                    delivery_id=row["delivery_id"],
                    run_id=run_id,
                    status="failed",
                    error=error[:2000],
                )

    def commit_generated_delivery(
        self,
        *,
        task_id: str,
        run_id: str,
        delivery_fingerprint: str,
        artifact_uri: str,
        snapshots: list[dict[str, Any]],
        watermarks: list[dict[str, Any]],
    ) -> None:
        now = _now()
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, run_id FROM deliveries WHERE delivery_fingerprint = ?",
                (delivery_fingerprint,),
            ).fetchone()
            if row is None:
                raise RuntimeError("delivery must be reserved before commit")
            if row["status"] not in {"pending", "generated", "delivered"}:
                raise RuntimeError(f"cannot commit delivery in {row['status']} state")
            if row["status"] in {"generated", "delivered"}:
                return
            if row["status"] == "pending" and row["run_id"] != run_id:
                raise RuntimeError("only the delivery owner can commit a pending delivery")

            if row["status"] == "pending":
                connection.execute(
                    """
                    UPDATE deliveries
                    SET status = 'generated', artifact_uri = ?, error = NULL,
                        generated_at = COALESCE(generated_at, ?), updated_at = ?
                    WHERE delivery_fingerprint = ? AND status = 'pending'
                    """,
                    (artifact_uri, now, now, delivery_fingerprint),
                )
                delivery = connection.execute(
                    "SELECT delivery_id FROM deliveries WHERE delivery_fingerprint = ?",
                    (delivery_fingerprint,),
                ).fetchone()
                self._record_delivery_event(
                    connection,
                    delivery_id=delivery["delivery_id"],
                    run_id=run_id,
                    status="generated",
                    artifact_uri=artifact_uri,
                )
            self._commit_snapshots(connection, task_id, snapshots, now)
            self._commit_watermarks(connection, task_id, watermarks, now)

    def commit_watermarks(
        self,
        task_id: str,
        watermarks: list[dict[str, Any]],
    ) -> None:
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._commit_watermarks(connection, task_id, watermarks, _now())

    def commit_observations_and_watermarks(
        self,
        task_id: str,
        snapshots: list[dict[str, Any]],
        watermarks: list[dict[str, Any]],
    ) -> None:
        now = _now()
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for snapshot in snapshots:
                self._commit_notice_snapshots(connection, task_id, snapshot, now)
            self._commit_watermarks(connection, task_id, watermarks, now)

    def create_subscription(
        self,
        *,
        task_id: str,
        query: str,
        frequency: str,
        timezone_name: str,
        local_time: str,
        weekly_day: str | None,
        run_at: datetime | None,
        next_run_at: datetime,
        now: datetime,
        max_retries: int,
        retry_backoff_seconds: int,
    ) -> dict[str, Any]:
        now_text = _utc_timestamp(now)
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO subscriptions(
                    task_id, query, frequency, timezone, local_time, weekly_day,
                    run_at, next_run_at, status, retry_count, max_retries,
                    retry_backoff_seconds, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', 0, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    query,
                    frequency,
                    timezone_name,
                    local_time,
                    weekly_day,
                    _utc_timestamp(run_at) if run_at is not None else None,
                    _utc_timestamp(next_run_at),
                    max_retries,
                    retry_backoff_seconds,
                    now_text,
                    now_text,
                ),
            )
            connection.execute(
                """
                INSERT INTO tasks(task_id, query, frequency, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    query = excluded.query,
                    frequency = excluded.frequency
                """,
                (task_id, query, frequency, now_text),
            )
            self._ensure_task_identity(connection, task_id, now_text)
            row = connection.execute(
                "SELECT * FROM subscriptions WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return dict(row)

    def get_subscription(self, task_id: str) -> dict[str, Any] | None:
        with connect() as connection:
            row = connection.execute(
                "SELECT * FROM subscriptions WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_subscriptions(self) -> list[dict[str, Any]]:
        with connect() as connection:
            rows = connection.execute(
                "SELECT * FROM subscriptions ORDER BY created_at, task_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def claim_due_subscription(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_duration: timedelta,
    ) -> dict[str, Any] | None:
        now_text = _utc_timestamp(now)
        lease_expires_at = _utc_timestamp(now + lease_duration)
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM subscriptions
                WHERE status = 'active'
                  AND next_run_at <= ?
                  AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                ORDER BY next_run_at, created_at, task_id
                LIMIT 1
                """,
                (now_text, now_text),
            ).fetchone()
            if row is None:
                return None
            task_id = row["task_id"]
            updated = connection.execute(
                """
                UPDATE subscriptions
                SET lease_owner = ?, lease_expires_at = ?, updated_at = ?
                WHERE task_id = ? AND status = 'active'
                  AND next_run_at <= ?
                  AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                """,
                (worker_id, lease_expires_at, now_text, task_id, now_text, now_text),
            ).rowcount
            if updated != 1:
                return None
            connection.execute(
                """
                UPDATE schedule_runs
                SET status = 'lease_expired', completed_at = ?,
                    error = 'worker lease expired before completion'
                WHERE task_id = ? AND status = 'running'
                """,
                (now_text, task_id),
            )
            run_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO schedule_runs(
                    run_id, task_id, scheduled_for, worker_id, status,
                    retry_count, started_at
                ) VALUES (?, ?, ?, ?, 'running', ?, ?)
                """,
                (
                    run_id,
                    task_id,
                    row["next_run_at"],
                    worker_id,
                    row["retry_count"],
                    now_text,
                ),
            )
            claimed = connection.execute(
                "SELECT * FROM subscriptions WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        result = dict(claimed)
        result["run_id"] = run_id
        result["scheduled_for"] = row["next_run_at"]
        return result

    def list_schedule_runs(self, task_id: str) -> list[dict[str, Any]]:
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM schedule_runs
                WHERE task_id = ?
                ORDER BY started_at, run_id
                """,
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def pause_subscription(self, task_id: str, *, now: datetime) -> dict[str, Any] | None:
        with connect() as connection:
            updated = connection.execute(
                """
                UPDATE subscriptions
                SET status = 'paused', updated_at = ?
                WHERE task_id = ? AND status = 'active'
                """,
                (_utc_timestamp(now), task_id),
            ).rowcount
            row = connection.execute(
                "SELECT * FROM subscriptions WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        if updated == 0 and row["status"] != "paused":
            raise ValueError(f"cannot pause a {row['status']} subscription")
        return dict(row)

    def resume_subscription(
        self,
        task_id: str,
        *,
        next_run_at: datetime,
        now: datetime,
    ) -> dict[str, Any] | None:
        now_text = _utc_timestamp(now)
        with connect() as connection:
            row = connection.execute(
                "SELECT * FROM subscriptions WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                return None
            if row["status"] not in {"paused", "failed"}:
                raise ValueError(f"cannot resume a {row['status']} subscription")
            if row["lease_expires_at"] is not None and row["lease_expires_at"] > now_text:
                raise RuntimeError("subscription is still owned by a running worker")
            connection.execute(
                """
                UPDATE subscriptions
                SET status = 'active', next_run_at = ?, retry_count = 0,
                    last_error = NULL, lease_owner = NULL,
                    lease_expires_at = NULL, updated_at = ?
                WHERE task_id = ?
                """,
                (_utc_timestamp(next_run_at), now_text, task_id),
            )
            restored = connection.execute(
                "SELECT * FROM subscriptions WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return dict(restored)

    def delete_subscription(self, task_id: str) -> bool:
        with connect() as connection:
            return connection.execute(
                "DELETE FROM subscriptions WHERE task_id = ?",
                (task_id,),
            ).rowcount == 1

    def renew_subscription_lease(
        self,
        *,
        task_id: str,
        worker_id: str,
        now: datetime,
        lease_duration: timedelta,
    ) -> bool:
        with connect() as connection:
            return connection.execute(
                """
                UPDATE subscriptions
                SET lease_expires_at = ?, updated_at = ?
                WHERE task_id = ? AND lease_owner = ?
                  AND status IN ('active', 'paused')
                """,
                (
                    _utc_timestamp(now + lease_duration),
                    _utc_timestamp(now),
                    task_id,
                    worker_id,
                ),
            ).rowcount == 1

    def complete_schedule_run(
        self,
        *,
        task_id: str,
        run_id: str,
        worker_id: str,
        now: datetime,
        next_run_at: datetime | None,
    ) -> bool:
        now_text = _utc_timestamp(now)
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT frequency, status, lease_owner FROM subscriptions WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row is None or row["lease_owner"] != worker_id:
                return False
            if row["frequency"] == "once":
                status = "completed"
            else:
                status = "paused" if row["status"] == "paused" else "active"
            connection.execute(
                """
                UPDATE subscriptions
                SET status = ?, next_run_at = COALESCE(?, next_run_at),
                    retry_count = 0, last_run_at = ?, last_error = NULL,
                    lease_owner = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE task_id = ? AND lease_owner = ?
                """,
                (
                    status,
                    _utc_timestamp(next_run_at) if next_run_at is not None else None,
                    now_text,
                    now_text,
                    task_id,
                    worker_id,
                ),
            )
            connection.execute(
                """
                UPDATE schedule_runs
                SET status = 'succeeded', completed_at = ?, error = NULL
                WHERE run_id = ? AND task_id = ? AND status = 'running'
                """,
                (now_text, run_id, task_id),
            )
        return True

    def fail_schedule_run(
        self,
        *,
        task_id: str,
        run_id: str,
        worker_id: str,
        now: datetime,
        error: str,
    ) -> bool:
        now_text = _utc_timestamp(now)
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT status, retry_count, max_retries, retry_backoff_seconds,
                       lease_owner
                FROM subscriptions WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if row is None or row["lease_owner"] != worker_id:
                return False
            retry_count = row["retry_count"] + 1
            if row["status"] == "paused":
                status = "paused"
            else:
                status = "active" if retry_count <= row["max_retries"] else "failed"
            delay = row["retry_backoff_seconds"] * (2 ** (retry_count - 1))
            retry_at = now + timedelta(seconds=delay)
            connection.execute(
                """
                UPDATE subscriptions
                SET status = ?, retry_count = ?, next_run_at = ?, last_run_at = ?,
                    last_error = ?, lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = ?
                WHERE task_id = ? AND lease_owner = ?
                """,
                (
                    status,
                    retry_count,
                    _utc_timestamp(retry_at),
                    now_text,
                    error[:2000],
                    now_text,
                    task_id,
                    worker_id,
                ),
            )
            connection.execute(
                """
                UPDATE schedule_runs
                SET status = 'failed', completed_at = ?, error = ?
                WHERE run_id = ? AND task_id = ? AND status = 'running'
                """,
                (now_text, error[:2000], run_id, task_id),
            )
        return True

    def mark_schedule_run_failed(
        self,
        *,
        task_id: str,
        run_id: str,
        now: datetime,
        error: str,
    ) -> bool:
        with connect() as connection:
            return connection.execute(
                """
                UPDATE schedule_runs
                SET status = 'failed', completed_at = ?, error = ?
                WHERE run_id = ? AND task_id = ? AND status = 'running'
                """,
                (_utc_timestamp(now), error[:2000], run_id, task_id),
            ).rowcount == 1

    @staticmethod
    def _ensure_task_identity(connection: Any, task_id: str, now: str) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO task_identities(task_id, created_at)
            VALUES (?, ?)
            """,
            (task_id, now),
        )

    @staticmethod
    def _record_delivery_event(
        connection: Any,
        *,
        delivery_id: str,
        run_id: str,
        status: str,
        artifact_uri: str | None = None,
        error: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO delivery_events(
                event_id, delivery_id, status, run_id,
                artifact_uri, error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                delivery_id,
                status,
                run_id,
                artifact_uri,
                error,
                _audit_now(),
            ),
        )

    @staticmethod
    def _record_delivery_changes(
        connection: Any,
        *,
        delivery_id: str,
        changes: list[dict[str, Any]],
    ) -> None:
        canonical = _canonical_json(changes)
        fingerprint = _json_fingerprint(changes)
        connection.execute(
            """
            INSERT OR IGNORE INTO delivery_change_versions(
                change_version_id, delivery_id, change_fingerprint,
                changes_json, recorded_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                _stable_id(delivery_id, fingerprint),
                delivery_id,
                fingerprint,
                canonical,
                _audit_now(),
            ),
        )

    @staticmethod
    def _record_publication_payload(
        connection: Any,
        *,
        publication_id: str,
        notice_payload: dict[str, Any],
        now: str,
    ) -> None:
        canonical = _canonical_json(notice_payload)
        fingerprint = _json_fingerprint(notice_payload)
        existing = connection.execute(
            """
            SELECT 1 FROM publication_payload_versions
            WHERE publication_id = ? AND payload_fingerprint = ?
            """,
            (publication_id, fingerprint),
        ).fetchone()
        if existing is not None:
            return
        version = connection.execute(
            """
            SELECT COALESCE(MAX(version), 0) + 1
            FROM publication_payload_versions
            WHERE publication_id = ?
            """,
            (publication_id,),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO publication_payload_versions(
                payload_version_id, publication_id, version,
                payload_fingerprint, notice_json, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _stable_id(publication_id, fingerprint),
                publication_id,
                version,
                fingerprint,
                canonical,
                now,
            ),
        )

    @staticmethod
    def _record_attachment_state(
        connection: Any,
        *,
        attachment_pk: str,
        state: dict[str, Any],
        now: str,
    ) -> None:
        fingerprint = _json_fingerprint(state)
        existing = connection.execute(
            """
            SELECT 1 FROM attachment_versions
            WHERE attachment_pk = ? AND state_fingerprint = ?
            """,
            (attachment_pk, fingerprint),
        ).fetchone()
        if existing is not None:
            return
        version = connection.execute(
            """
            SELECT COALESCE(MAX(version), 0) + 1
            FROM attachment_versions
            WHERE attachment_pk = ?
            """,
            (attachment_pk,),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO attachment_versions(
                attachment_version_id, attachment_pk, version,
                state_fingerprint, status, media_type, size_bytes,
                content_sha256, fetched_at, failure_reason, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _stable_id(attachment_pk, fingerprint),
                attachment_pk,
                version,
                fingerprint,
                state["status"],
                state["media_type"],
                state["size_bytes"],
                state["content_sha256"],
                state["fetched_at"],
                state["failure_reason"],
                now,
            ),
        )
        connection.execute(
            """
            UPDATE attachments
            SET status = ?, media_type = ?, size_bytes = ?,
                content_sha256 = ?, fetched_at = ?, failure_reason = ?
            WHERE attachment_pk = ?
            """,
            (
                state["status"],
                state["media_type"],
                state["size_bytes"],
                state["content_sha256"],
                state["fetched_at"],
                state["failure_reason"],
                attachment_pk,
            ),
        )

    @staticmethod
    def _persist_tender_notice(
        connection: Any,
        notice: TenderNotice,
        *,
        collection_run_id: str | None,
        attachment_states: Mapping[str, AttachmentState] | None = None,
        response_metadata: SourceResponseMetadata | None = None,
    ) -> str:
        now = _now()
        notice_payload = TenderNotice.model_validate(
            notice.model_dump(mode="json")
        ).model_dump(mode="json")
        project_id = notice_payload["project_stable_fingerprint"]
        notice_event_id = notice_payload["notice_stable_fingerprint"]
        connection.execute(
            """
            INSERT OR IGNORE INTO projects(
                project_id, project_stable_fingerprint,
                fingerprint_version, created_at
            ) VALUES (?, ?, 'contract-v1', ?)
            """,
            (project_id, notice_payload["project_stable_fingerprint"], now),
        )
        existing_event = connection.execute(
            "SELECT project_id, notice_type FROM notice_events WHERE notice_event_id = ?",
            (notice_event_id,),
        ).fetchone()
        if existing_event is not None and (
            existing_event["project_id"] != project_id
            or existing_event["notice_type"] != notice_payload["notice_type"]
        ):
            raise ValueError(
                "notice identity is already bound to a different project or lifecycle type"
            )
        connection.execute(
            """
            INSERT OR IGNORE INTO notice_events(
                notice_event_id, project_id, notice_stable_fingerprint,
                fingerprint_version, notice_type, project_code, created_at
            ) VALUES (?, ?, ?, 'contract-v1', ?, ?, ?)
            """,
            (
                notice_event_id,
                project_id,
                notice_payload["notice_stable_fingerprint"],
                notice_payload["notice_type"],
                notice_payload["project_code"],
                now,
            ),
        )

        source = notice_payload["source"]
        source_id = source["source_id"]
        source_url = source["source_url"]
        publication_id = _stable_id(
            source_id,
            notice_payload["notice_id"],
            source_url,
            source["publication_role"],
            notice_payload["raw_content_fingerprint"],
        )
        existing_publication = connection.execute(
            """
            SELECT * FROM source_publications
            WHERE publication_id = ?
               OR (
                   source_id = ? AND notice_id = ? AND source_url = ?
                   AND publication_role = ?
                   AND raw_content_fingerprint = ?
               )
            """,
            (
                publication_id,
                source_id,
                notice_payload["notice_id"],
                source_url,
                source["publication_role"],
                notice_payload["raw_content_fingerprint"],
            ),
        ).fetchone()
        if existing_publication is not None:
            if existing_publication["notice_event_id"] != notice_event_id:
                raise ValueError(
                    "source publication identity is already bound to another notice"
                )
            publication_id = existing_publication["publication_id"]
        else:
            metadata_json = (
                _canonical_json(response_metadata.metadata)
                if response_metadata is not None
                and response_metadata.metadata is not None
                else None
            )
            connection.execute(
                """
                INSERT INTO source_publications(
                    publication_id, notice_id, notice_event_id,
                    source_id, source_name, source_url,
                    canonical_notice_url, source_notice_id, publication_role,
                    title, published_at, fetched_at, core_content,
                    raw_content_fingerprint, response_http_status,
                    response_content_type, response_etag,
                    response_last_modified, response_metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    publication_id,
                    notice_payload["notice_id"],
                    notice_event_id,
                    source_id,
                    source["source_name"],
                    source_url,
                    (
                        source["canonical_notice_url"]
                        if source["canonical_notice_url"] is not None
                        else None
                    ),
                    source["source_notice_id"],
                    source["publication_role"],
                    notice_payload["title"],
                    notice_payload["published_at"],
                    notice_payload["fetched_at"],
                    notice_payload["core_content"],
                    notice_payload["raw_content_fingerprint"],
                    response_metadata.http_status if response_metadata else None,
                    response_metadata.content_type if response_metadata else None,
                    response_metadata.etag if response_metadata else None,
                    response_metadata.last_modified if response_metadata else None,
                    metadata_json,
                    now,
                ),
            )

        Repository._record_publication_payload(
            connection,
            publication_id=publication_id,
            notice_payload=notice_payload,
            now=now,
        )

        if collection_run_id is not None:
            connection.execute(
                """
                INSERT OR IGNORE INTO collection_run_publications(
                    collection_run_id, publication_id, observed_at
                ) VALUES (?, ?, ?)
                """,
                (collection_run_id, publication_id, notice_payload["fetched_at"]),
            )

        states = attachment_states or {}
        attachment_pks: dict[str, str] = {}
        for attachment in notice_payload["attachments"]:
            attachment_id = attachment["attachment_id"]
            attachment_pk = _stable_id(publication_id, attachment_id)
            attachment_pks[attachment_id] = attachment_pk
            existing_attachment = connection.execute(
                "SELECT * FROM attachments WHERE attachment_pk = ?",
                (attachment_pk,),
            ).fetchone()
            explicit_state = states.get(attachment_id)
            if explicit_state is not None:
                attachment_state = {
                    "status": explicit_state.status,
                    "media_type": explicit_state.media_type or attachment["media_type"],
                    "size_bytes": explicit_state.size_bytes,
                    "content_sha256": (
                        explicit_state.content_sha256 or attachment["content_sha256"]
                    ),
                    "fetched_at": (
                        explicit_state.fetched_at.isoformat()
                        if explicit_state.fetched_at is not None
                        else attachment["fetched_at"]
                    ),
                    "failure_reason": explicit_state.failure_reason,
                }
            elif existing_attachment is not None:
                attachment_state = {
                    "status": existing_attachment["status"],
                    "media_type": existing_attachment["media_type"],
                    "size_bytes": existing_attachment["size_bytes"],
                    "content_sha256": existing_attachment["content_sha256"],
                    "fetched_at": existing_attachment["fetched_at"],
                    "failure_reason": existing_attachment["failure_reason"],
                }
            else:
                attachment_state = {
                    "status": (
                        "downloaded"
                        if attachment["content_sha256"] is not None
                        and attachment["fetched_at"] is not None
                        else "discovered"
                    ),
                    "media_type": attachment["media_type"],
                    "size_bytes": None,
                    "content_sha256": attachment["content_sha256"],
                    "fetched_at": attachment["fetched_at"],
                    "failure_reason": None,
                }
            connection.execute(
                """
                INSERT OR IGNORE INTO attachments(
                    attachment_pk, attachment_id, publication_id,
                    entry_url, name, status, media_type, size_bytes,
                    content_sha256, fetched_at, failure_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attachment_pk,
                    attachment_id,
                    publication_id,
                    attachment["url"],
                    attachment["name"],
                    attachment_state["status"],
                    attachment_state["media_type"],
                    attachment_state["size_bytes"],
                    attachment_state["content_sha256"],
                    attachment_state["fetched_at"],
                    attachment_state["failure_reason"],
                    now,
                ),
            )
            Repository._record_attachment_state(
                connection,
                attachment_pk=attachment_pk,
                state=attachment_state,
                now=now,
            )

        for evidence in notice_payload["evidence"]:
            if evidence["attachment_id"] is not None:
                attachment_pks[evidence["attachment_id"]]
            connection.execute(
                """
                INSERT OR IGNORE INTO field_evidence(
                    evidence_pk, evidence_id, publication_id, notice_event_id,
                    attachment_id, field_path, source_url, document_name,
                    page_number, section, locator, quote, fetched_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _stable_id(publication_id, evidence["evidence_id"]),
                    evidence["evidence_id"],
                    publication_id,
                    notice_event_id,
                    evidence["attachment_id"],
                    evidence["field_path"],
                    evidence["source_url"],
                    evidence["document_name"],
                    evidence["page_number"],
                    evidence["section"],
                    evidence["locator"],
                    evidence["quote"],
                    evidence["fetched_at"],
                    now,
                ),
            )
        return publication_id

    @staticmethod
    def _commit_snapshots(
        connection: Any,
        task_id: str,
        snapshots: list[dict[str, Any]],
        now: str,
    ) -> None:
        for snapshot in snapshots:
            project_fingerprint = snapshot["project_stable_fingerprint"]
            Repository._ensure_task_identity(connection, task_id, now)
            connection.execute(
                """
                INSERT OR IGNORE INTO projects(
                    project_id, project_stable_fingerprint,
                    fingerprint_version, created_at
                ) VALUES (?, ?, 'contract-v1', ?)
                """,
                (project_fingerprint, project_fingerprint, now),
            )
            current = connection.execute(
                """
                SELECT version, snapshot_fingerprint
                FROM project_snapshots
                WHERE task_id = ? AND project_id = ?
                """,
                (task_id, snapshot["project_id"]),
            ).fetchone()
            if current is not None and current["snapshot_fingerprint"] == snapshot["snapshot_fingerprint"]:
                continue
            version = (current["version"] if current is not None else 0) + 1
            canonical_snapshot = _canonical_json(snapshot)
            connection.execute(
                """
                INSERT INTO project_snapshot_versions(
                    snapshot_id, task_id, project_id, snapshot_fingerprint,
                    version, snapshot_json, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _stable_id(
                        task_id,
                        project_fingerprint,
                        snapshot["snapshot_fingerprint"],
                    ),
                    task_id,
                    project_fingerprint,
                    snapshot["snapshot_fingerprint"],
                    version,
                    canonical_snapshot,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO project_snapshots(
                    task_id, project_id, facts_json, updated_at,
                    project_stable_fingerprint, snapshot_fingerprint,
                    snapshot_json, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id, project_id) DO UPDATE SET
                    facts_json = excluded.facts_json,
                    updated_at = excluded.updated_at,
                    project_stable_fingerprint = excluded.project_stable_fingerprint,
                    snapshot_fingerprint = excluded.snapshot_fingerprint,
                    snapshot_json = excluded.snapshot_json,
                    version = excluded.version
                """,
                (
                    task_id,
                    snapshot["project_id"],
                    _canonical_json(snapshot["facts"]),
                    now,
                    project_fingerprint,
                    snapshot["snapshot_fingerprint"],
                    canonical_snapshot,
                    version,
                ),
            )
            Repository._commit_notice_snapshots(connection, task_id, snapshot, now)

    @staticmethod
    def _commit_notice_snapshots(
        connection: Any,
        task_id: str,
        snapshot: dict[str, Any],
        now: str,
    ) -> None:
        project_fingerprint = snapshot["project_stable_fingerprint"]
        for notice in snapshot["notices"]:
            validated_notice = TenderNotice.model_validate(notice)
            notice_payload = validated_notice.model_dump(mode="json")
            Repository._persist_tender_notice(
                connection,
                validated_notice,
                collection_run_id=None,
            )
            canonical = _canonical_json(notice_payload)
            notice_snapshot_fingerprint = _json_fingerprint(notice_payload)
            notice_fingerprint = notice_payload["notice_stable_fingerprint"]
            existing = connection.execute(
                """
                SELECT 1 FROM notice_snapshots
                WHERE task_id = ? AND notice_stable_fingerprint = ?
                  AND snapshot_fingerprint = ?
                """,
                (task_id, notice_fingerprint, notice_snapshot_fingerprint),
            ).fetchone()
            if existing is not None:
                continue
            next_version = connection.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1
                FROM notice_snapshots
                WHERE task_id = ? AND notice_stable_fingerprint = ?
                """,
                (task_id, notice_fingerprint),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO notice_snapshots(
                    task_id, project_stable_fingerprint,
                    notice_stable_fingerprint, snapshot_fingerprint,
                    version, notice_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    project_fingerprint,
                    notice_fingerprint,
                    notice_snapshot_fingerprint,
                    next_version,
                    canonical,
                    now,
                ),
            )

    @staticmethod
    def _commit_watermarks(
        connection: Any,
        task_id: str,
        watermarks: list[dict[str, Any]],
        now: str,
    ) -> None:
        for watermark in watermarks:
            Repository._ensure_task_identity(connection, task_id, now)
            row = connection.execute(
                """
                SELECT watermark_json FROM source_watermarks
                WHERE task_id = ? AND source_id = ?
                """,
                (task_id, watermark["source_id"]),
            ).fetchone()
            merged = dict(watermark)
            if row is not None:
                previous = json.loads(row["watermark_json"])
                for field in ("processed_through", "max_published_at", "max_fetched_at"):
                    candidates = [
                        value
                        for value in (previous.get(field), watermark.get(field))
                        if value is not None
                    ]
                    merged[field] = max(
                        candidates,
                        key=lambda value: datetime.fromisoformat(value),
                        default=None,
                    )
                merged["notice_stable_fingerprints"] = sorted(
                    set(previous.get("notice_stable_fingerprints", []))
                    | set(watermark.get("notice_stable_fingerprints", []))
                )
            connection.execute(
                """
                INSERT INTO source_watermarks(task_id, source_id, watermark_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id, source_id) DO UPDATE SET
                    watermark_json = excluded.watermark_json,
                    updated_at = excluded.updated_at
                """,
                (
                    task_id,
                    watermark["source_id"],
                    _canonical_json(merged),
                    now,
                ),
            )
            cursor_published_at = (
                merged.get("max_published_at")
                or merged.get("processed_through")
                or merged.get("max_fetched_at")
            )
            notice_fingerprints = merged.get("notice_stable_fingerprints", [])
            cursor_notice_fingerprint = (
                notice_fingerprints[-1] if notice_fingerprints else None
            )
            if cursor_published_at is not None and (
                merged.get("source_notice_id") is not None
                or merged.get("source_url") is not None
                or cursor_notice_fingerprint is not None
            ):
                Repository._write_watermark(
                    connection,
                    task_id=task_id,
                    source_id=watermark["source_id"],
                    cursor=WatermarkCursor(
                        published_at=datetime.fromisoformat(cursor_published_at),
                        source_notice_id=merged.get("source_notice_id"),
                        source_url=merged.get("source_url"),
                        notice_stable_fingerprint=cursor_notice_fingerprint,
                    ),
                    collection_run_id=None,
                    watermark_payload=merged,
                    now=now,
                    update_current=False,
                )

    @staticmethod
    def _write_watermark(
        connection: Any,
        *,
        task_id: str,
        source_id: str,
        cursor: WatermarkCursor,
        collection_run_id: str | None,
        watermark_payload: dict[str, Any],
        now: str,
        update_current: bool = True,
    ) -> None:
        cursor_published_at = cursor.published_at.isoformat(timespec="seconds")
        identity_payload = {
            "published_at": cursor_published_at,
            "source_notice_id": cursor.source_notice_id,
            "source_url": cursor.source_url,
            "notice_stable_fingerprint": cursor.notice_stable_fingerprint,
        }
        identity_fingerprint = _json_fingerprint(identity_payload)
        canonical = _canonical_json(watermark_payload)
        Repository._ensure_task_identity(connection, task_id, now)
        connection.execute(
            """
            INSERT OR IGNORE INTO source_watermark_versions(
                watermark_id, task_id, source_id, collection_run_id,
                cursor_published_at, cursor_source_notice_id,
                cursor_source_url, cursor_notice_fingerprint,
                cursor_identity_fingerprint, watermark_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _stable_id(task_id, source_id, identity_fingerprint),
                task_id,
                source_id,
                collection_run_id,
                cursor_published_at,
                cursor.source_notice_id,
                cursor.source_url,
                cursor.notice_stable_fingerprint,
                identity_fingerprint,
                canonical,
                now,
            ),
        )
        if not update_current:
            return

        current = connection.execute(
            """
            SELECT watermark_json FROM source_watermarks
            WHERE task_id = ? AND source_id = ?
            """,
            (task_id, source_id),
        ).fetchone()
        if current is not None:
            previous = json.loads(current["watermark_json"])
            previous_cursor = previous.get("published_at") or previous.get(
                "max_published_at"
            )
            if (
                previous_cursor is not None
                and datetime.fromisoformat(previous_cursor)
                > datetime.fromisoformat(cursor_published_at)
            ):
                return
        connection.execute(
            """
            INSERT INTO source_watermarks(task_id, source_id, watermark_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(task_id, source_id) DO UPDATE SET
                watermark_json = excluded.watermark_json,
                updated_at = excluded.updated_at
            """,
            (task_id, source_id, canonical, now),
        )

    @staticmethod
    def _delivery_row(row: Any) -> dict[str, Any]:
        result = dict(row)
        result["changes"] = json.loads(result.pop("changes_json"))
        result["project_stable_fingerprints"] = json.loads(
            result.pop("project_fingerprints_json")
        )
        result["notice_stable_fingerprints"] = json.loads(
            result.pop("notice_fingerprints_json")
        )
        return result

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with connect() as connection:
            rows = connection.execute(
                "SELECT result_json FROM runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["result_json"]) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return json.loads(row["result_json"]) if row is not None else None

    def list_report_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT runs.run_id, runs.task_id, runs.status,
                       runs.result_json, runs.created_at
                FROM runs
                LEFT JOIN hidden_report_runs hidden
                  ON hidden.run_id = runs.run_id
                WHERE hidden.run_id IS NULL
                ORDER BY runs.created_at DESC, runs.run_id DESC
                LIMIT ?
                """,
                (max(limit * 8, limit),),
            ).fetchall()
        items: list[dict[str, Any]] = []
        latest_by_identity: dict[str, datetime] = {}
        for row in rows:
            result = json.loads(row["result_json"])
            query = str(result.get("query", ""))
            frequency = str(result.get("frequency", "once"))
            identity = query
            created_at = datetime.fromisoformat(row["created_at"])
            previous = latest_by_identity.get(identity) if identity else None
            if previous is not None and abs((previous - created_at).total_seconds()) <= 5:
                continue
            if identity:
                latest_by_identity[identity] = created_at
            items.append(
                {
                    "run_id": row["run_id"],
                    "task_id": row["task_id"],
                    "query": query,
                    "frequency": frequency,
                    "run_status": row["status"],
                    "created_at": row["created_at"],
                    "project_count": len(result.get("projects", [])),
                    "report": result.get("report"),
                    "ai_report": result.get("ai_report") or {"status": "not_generated"},
                }
            )
            if len(items) >= limit:
                break
        return items

    def hide_report_run(self, run_id: str) -> bool:
        """Hide a visible run and any same-query duplicates created seconds apart."""

        with connect() as connection:
            target = connection.execute(
                "SELECT run_id, result_json, created_at FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if target is None:
                return False
            target_result = json.loads(target["result_json"])
            target_identity = str(target_result.get("query", ""))
            target_created_at = datetime.fromisoformat(target["created_at"])
            duplicates = [run_id]
            if target_identity:
                for candidate in connection.execute(
                    "SELECT run_id, result_json, created_at FROM runs"
                ).fetchall():
                    candidate_result = json.loads(candidate["result_json"])
                    candidate_identity = str(candidate_result.get("query", ""))
                    candidate_created_at = datetime.fromisoformat(candidate["created_at"])
                    if (
                        candidate_identity == target_identity
                        and abs((candidate_created_at - target_created_at).total_seconds()) <= 5
                    ):
                        duplicates.append(candidate["run_id"])
            connection.executemany(
                """
                INSERT INTO hidden_report_runs(run_id, hidden_at)
                VALUES (?, ?)
                ON CONFLICT(run_id) DO UPDATE SET hidden_at = excluded.hidden_at
                """,
                [(duplicate_run_id, _now()) for duplicate_run_id in duplicates],
            )
        return True

    def save_project_profiles(self, run_id: str, profiles: list[dict[str, Any]]) -> None:
        with connect() as connection:
            connection.executemany(
                """
                INSERT INTO project_profiles(run_id, project_id, project_json, modules_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id, project_id)
                DO UPDATE SET project_json = excluded.project_json,
                              modules_json = excluded.modules_json,
                              updated_at = excluded.updated_at
                """,
                [
                    (
                        run_id,
                        profile["project_id"],
                        json.dumps({key: value for key, value in profile.items() if key != "modules"}, ensure_ascii=False),
                        json.dumps(profile["modules"], ensure_ascii=False),
                        _now(),
                    )
                    for profile in profiles
                ],
            )

    def list_project_profiles(self, run_id: str) -> list[dict[str, Any]]:
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT project_json, modules_json
                FROM project_profiles
                WHERE run_id = ?
                ORDER BY json_extract(project_json, '$.published_at') DESC
                """,
                (run_id,),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            project = json.loads(row["project_json"])
            project["module_count"] = len(json.loads(row["modules_json"]))
            items.append(project)
        return items

    def get_project_profile(self, run_id: str, project_id: str) -> dict[str, Any] | None:
        with connect() as connection:
            row = connection.execute(
                """
                SELECT project_json, modules_json
                FROM project_profiles
                WHERE run_id = ? AND project_id = ?
                """,
                (run_id, project_id),
            ).fetchone()
        if row is None:
            return None
        project = json.loads(row["project_json"])
        project["modules"] = json.loads(row["modules_json"])
        return project
