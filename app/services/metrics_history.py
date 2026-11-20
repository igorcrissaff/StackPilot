from __future__ import annotations

import sqlite3
from pathlib import Path

from pydantic import BaseModel


class HistoryBucket(BaseModel):
    bucket_start: int
    cpu_percent: float
    memory_percent: float
    memory_used: int
    memory_total: int
    swap_percent: float
    swap_used: int
    swap_total: int
    disk_percent: float
    disk_used: int
    disk_total: int
    load_1: float | None
    load_5: float | None
    load_15: float | None
    sample_count: int


def _weighted(previous: float, current: float, previous_count: int, current_count: int) -> float:
    total = previous_count + current_count
    return (previous * previous_count + current * current_count) / total


def _weighted_optional(
    previous: float | None, current: float | None, previous_count: int, current_count: int
) -> float | None:
    if previous is None and current is None:
        return None
    if previous is None:
        return current
    if current is None:
        return previous
    return _weighted(previous, current, previous_count, current_count)


class MetricsHistoryRepository:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metrics_history (
                    bucket_start INTEGER PRIMARY KEY,
                    cpu_percent REAL NOT NULL,
                    memory_percent REAL NOT NULL,
                    memory_used INTEGER NOT NULL,
                    memory_total INTEGER NOT NULL,
                    swap_percent REAL NOT NULL,
                    swap_used INTEGER NOT NULL,
                    swap_total INTEGER NOT NULL,
                    disk_percent REAL NOT NULL,
                    disk_used INTEGER NOT NULL,
                    disk_total INTEGER NOT NULL,
                    load_1 REAL,
                    load_5 REAL,
                    load_15 REAL,
                    sample_count INTEGER NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_bucket(self, bucket: HistoryBucket) -> None:
        conn = self._connect()
        try:
            previous = conn.execute(
                "SELECT * FROM metrics_history WHERE bucket_start = ?",
                (bucket.bucket_start,),
            ).fetchone()

            if previous is None:
                conn.execute(
                    """
                    INSERT INTO metrics_history (
                        bucket_start, cpu_percent, memory_percent, memory_used,
                        memory_total, swap_percent, swap_used, swap_total,
                        disk_percent, disk_used, disk_total, load_1, load_5,
                        load_15, sample_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bucket.bucket_start,
                        bucket.cpu_percent,
                        bucket.memory_percent,
                        bucket.memory_used,
                        bucket.memory_total,
                        bucket.swap_percent,
                        bucket.swap_used,
                        bucket.swap_total,
                        bucket.disk_percent,
                        bucket.disk_used,
                        bucket.disk_total,
                        bucket.load_1,
                        bucket.load_5,
                        bucket.load_15,
                        bucket.sample_count,
                    ),
                )
            else:
                pc = int(previous["sample_count"])
                cc = bucket.sample_count
                conn.execute(
                    """
                    UPDATE metrics_history SET
                        cpu_percent = ?, memory_percent = ?, memory_used = ?,
                        memory_total = ?, swap_percent = ?, swap_used = ?,
                        swap_total = ?, disk_percent = ?, disk_used = ?,
                        disk_total = ?, load_1 = ?, load_5 = ?, load_15 = ?,
                        sample_count = ?
                    WHERE bucket_start = ?
                    """,
                    (
                        _weighted(previous["cpu_percent"], bucket.cpu_percent, pc, cc),
                        _weighted(previous["memory_percent"], bucket.memory_percent, pc, cc),
                        int(round(_weighted(previous["memory_used"], bucket.memory_used, pc, cc))),
                        int(round(_weighted(previous["memory_total"], bucket.memory_total, pc, cc))),
                        _weighted(previous["swap_percent"], bucket.swap_percent, pc, cc),
                        int(round(_weighted(previous["swap_used"], bucket.swap_used, pc, cc))),
                        int(round(_weighted(previous["swap_total"], bucket.swap_total, pc, cc))),
                        _weighted(previous["disk_percent"], bucket.disk_percent, pc, cc),
                        int(round(_weighted(previous["disk_used"], bucket.disk_used, pc, cc))),
                        int(round(_weighted(previous["disk_total"], bucket.disk_total, pc, cc))),
                        _weighted_optional(previous["load_1"], bucket.load_1, pc, cc),
                        _weighted_optional(previous["load_5"], bucket.load_5, pc, cc),
                        _weighted_optional(previous["load_15"], bucket.load_15, pc, cc),
                        pc + cc,
                        bucket.bucket_start,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def list_buckets(self, start: int | None = None, end: int | None = None) -> list[HistoryBucket]:
        query = "SELECT * FROM metrics_history"
        clauses = []
        params: list[int] = []
        if start is not None:
            clauses.append("bucket_start >= ?")
            params.append(start)
        if end is not None:
            clauses.append("bucket_start < ?")
            params.append(end)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY bucket_start ASC"

        conn = self._connect()
        try:
            rows = conn.execute(query, tuple(params)).fetchall()
        finally:
            conn.close()

        return [
            HistoryBucket(
                bucket_start=int(row["bucket_start"]),
                cpu_percent=float(row["cpu_percent"]),
                memory_percent=float(row["memory_percent"]),
                memory_used=int(row["memory_used"]),
                memory_total=int(row["memory_total"]),
                swap_percent=float(row["swap_percent"]),
                swap_used=int(row["swap_used"]),
                swap_total=int(row["swap_total"]),
                disk_percent=float(row["disk_percent"]),
                disk_used=int(row["disk_used"]),
                disk_total=int(row["disk_total"]),
                load_1=row["load_1"],
                load_5=row["load_5"],
                load_15=row["load_15"],
                sample_count=int(row["sample_count"]),
            )
            for row in rows
        ]
