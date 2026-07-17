"""Backfill tombstones for duplicated report-history rows already hidden once."""

from __future__ import annotations

from datetime import datetime
import json
import sqlite3


CHECKSUM = "93c397e1e03cd623f7bc58edce66903fdb807d07eb735eb9a474d38703f8dc37"


def upgrade(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT runs.run_id, runs.result_json, runs.created_at,
               hidden_report_runs.hidden_at
        FROM runs
        LEFT JOIN hidden_report_runs
          ON hidden_report_runs.run_id = runs.run_id
        """
    ).fetchall()

    records: list[dict[str, object]] = []
    for row in rows:
        try:
            result = json.loads(row["result_json"])
            created_at = datetime.fromisoformat(row["created_at"])
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        query = str(result.get("query", ""))
        if not query:
            continue
        records.append(
            {
                "run_id": row["run_id"],
                "query": query,
                "created_at": created_at,
                "hidden_at": row["hidden_at"],
            }
        )

    tombstones: dict[str, str] = {}
    for hidden in records:
        hidden_at = hidden["hidden_at"]
        if not isinstance(hidden_at, str):
            continue
        for candidate in records:
            if candidate["query"] != hidden["query"]:
                continue
            seconds_apart = abs(
                (candidate["created_at"] - hidden["created_at"]).total_seconds()
            )
            if seconds_apart <= 5:
                tombstones[str(candidate["run_id"])] = hidden_at

    connection.executemany(
        """
        INSERT INTO hidden_report_runs(run_id, hidden_at)
        VALUES (?, ?)
        ON CONFLICT(run_id) DO NOTHING
        """,
        tombstones.items(),
    )
