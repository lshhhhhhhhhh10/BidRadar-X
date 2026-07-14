from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

from .database import connect, initialize_database


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


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

    def save_run(self, state: dict[str, Any]) -> None:
        with connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO runs(run_id, task_id, status, result_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    state["run_id"],
                    state["task_id"],
                    state["status"],
                    json.dumps(state, ensure_ascii=False),
                    _now(),
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
                    (task_id, item["project_id"], json.dumps(item["facts"], ensure_ascii=False), _now())
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
                        json.dumps(changes, ensure_ascii=False, sort_keys=True),
                        json.dumps(sorted(project_stable_fingerprints or [])),
                        json.dumps(sorted(notice_stable_fingerprints or [])),
                        now,
                        now,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM deliveries WHERE delivery_id = ?",
                    (delivery_id,),
                ).fetchone()
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
            connection.execute(
                """
                UPDATE deliveries
                SET status = 'failed', error = ?, updated_at = ?
                WHERE delivery_fingerprint = ? AND run_id = ? AND status = 'pending'
                """,
                (error[:2000], _now(), delivery_fingerprint, run_id),
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
            if row["status"] == "pending" and row["run_id"] != run_id:
                raise RuntimeError("only the delivery owner can commit a pending delivery")

            connection.execute(
                """
                UPDATE deliveries
                SET status = 'generated', artifact_uri = ?, error = NULL,
                    generated_at = COALESCE(generated_at, ?), updated_at = ?
                WHERE delivery_fingerprint = ?
                """,
                (artifact_uri, now, now, delivery_fingerprint),
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
    def _commit_snapshots(
        connection: Any,
        task_id: str,
        snapshots: list[dict[str, Any]],
        now: str,
    ) -> None:
        for snapshot in snapshots:
            project_fingerprint = snapshot["project_stable_fingerprint"]
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
                    json.dumps(snapshot["facts"], ensure_ascii=False, sort_keys=True),
                    now,
                    project_fingerprint,
                    snapshot["snapshot_fingerprint"],
                    json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
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
            canonical = json.dumps(notice, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            notice_snapshot_fingerprint = sha256(canonical.encode("utf-8")).hexdigest()
            notice_fingerprint = notice["notice_stable_fingerprint"]
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
                    json.dumps(merged, ensure_ascii=False, sort_keys=True),
                    now,
                ),
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
                SELECT run_id, task_id, status, result_json, created_at
                FROM runs
                ORDER BY created_at DESC, run_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            result = json.loads(row["result_json"])
            items.append(
                {
                    "run_id": row["run_id"],
                    "task_id": row["task_id"],
                    "query": result.get("query", ""),
                    "frequency": result.get("frequency", "once"),
                    "run_status": row["status"],
                    "created_at": row["created_at"],
                    "project_count": len(result.get("projects", [])),
                    "report": result.get("report"),
                }
            )
        return items

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
