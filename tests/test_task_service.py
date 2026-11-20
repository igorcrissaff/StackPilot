import asyncio
import sqlite3
from datetime import datetime, timezone

import pytest

from app.services.task_service import TaskService


def test_enqueue_sync_task_completes(tmp_path):
    async def _run():
        svc = TaskService(tmp_path / "stackpilot.db")
        svc.init_db()

        def work():
            return "ok"

        record = svc.enqueue("Pull da imagem nginx:latest", work)
        assert record.status == "running"

        await asyncio.sleep(0.05)

        tasks = svc.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].title == "Pull da imagem nginx:latest"
        assert tasks[0].status == "completed"
        assert tasks[0].finished_at is not None

    asyncio.run(_run())


def test_enqueue_failing_task_marks_failed(tmp_path):
    async def _run():
        svc = TaskService(tmp_path / "stackpilot.db")
        svc.init_db()

        def failing_work():
            raise RuntimeError("boom")

        svc.enqueue("Remover imagem quebrada", failing_work)
        await asyncio.sleep(0.05)

        tasks = svc.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].status == "failed"
        assert tasks[0].finished_at is not None

    asyncio.run(_run())


def test_mark_interrupted_tasks(tmp_path):
    db_path = tmp_path / "stackpilot.db"
    svc = TaskService(db_path)
    svc.init_db()

    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO tasks (id, title, status, created_at, finished_at) VALUES (?, ?, ?, ?, ?)",
            ("task-1", "Compose up", "running", now, None),
        )
        conn.commit()

    updated = svc.mark_interrupted_tasks()
    assert updated == 1

    tasks = svc.list_tasks()
    assert len(tasks) == 1
    assert tasks[0].status == "failed"
    assert tasks[0].finished_at is not None
