import asyncio
import inspect
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class TaskRecord:
    id: str
    title: str
    status: str
    created_at: str
    finished_at: str | None = None


class TaskService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._background_tasks: set[asyncio.Task[Any]] = set()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    finished_at TEXT
                )
                """
            )
            conn.commit()

    def mark_interrupted_tasks(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET status = 'failed', finished_at = ? WHERE status = 'running'",
                (now,),
            )
            conn.commit()
            return cursor.rowcount

    def _insert_task(self, record: TaskRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO tasks (id, title, status, created_at, finished_at) VALUES (?, ?, ?, ?, ?)",
                (record.id, record.title, record.status, record.created_at, record.finished_at),
            )
            conn.commit()

    def _update_status(self, task_id: str, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, finished_at = ? WHERE id = ?",
                (status, now, task_id),
            )
            conn.commit()

    def enqueue(self, title: str, fn: Callable[[], Any]) -> TaskRecord:
        self.init_db()
        record = TaskRecord(
            id=str(uuid.uuid4()),
            title=title,
            status="running",
            created_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
        )
        self._insert_task(record)

        async def _runner() -> None:
            try:
                if inspect.iscoroutinefunction(fn):
                    await fn()
                else:
                    result = await asyncio.to_thread(fn)
                    if inspect.isawaitable(result):
                        await result
                self._update_status(record.id, "completed")
            except Exception:
                logger.exception("Background task %s (%s) failed", record.id, title)
                self._update_status(record.id, "failed")

        task = asyncio.create_task(_runner())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return record

    def list_tasks(self, limit: int = 50) -> list[TaskRecord]:
        self.init_db()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, status, created_at, finished_at FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            TaskRecord(
                id=row["id"],
                title=row["title"],
                status=row["status"],
                created_at=row["created_at"],
                finished_at=row["finished_at"],
            )
            for row in rows
        ]
