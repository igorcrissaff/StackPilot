import pytest
from fastapi.testclient import TestClient

from app.auth import require_auth
from app.main import app


@pytest.fixture
def auth_client():
    app.dependency_overrides[require_auth] = lambda: "admin"
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_tasks_page_requires_auth():
    client = TestClient(app)
    resp = client.get("/tasks", follow_redirects=False)
    assert resp.status_code in (302, 303, 401)


def test_tasks_page_renders(auth_client):
    resp = auth_client.get("/tasks")
    assert resp.status_code == 200
    assert "Tarefas" in resp.text


def test_tasks_list_partial_renders_tasks(auth_client, tmp_path):
    from app.services.task_service import TaskService

    svc = TaskService(tmp_path / "stackpilot.db")
    svc.init_db()
    svc._insert_task(
        __import__("app.services.task_service", fromlist=["TaskRecord"]).TaskRecord(
            id="t1",
            title="Pull da imagem nginx:latest",
            status="running",
            created_at="2026-11-20T12:00:00+00:00",
        )
    )
    app.state.task_service = svc

    resp = auth_client.get("/tasks/list")
    assert resp.status_code == 200
    assert "Pull da imagem nginx:latest" in resp.text
    assert "Em andamento" in resp.text
