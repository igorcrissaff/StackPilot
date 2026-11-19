from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.dependencies import (
    get_compose_service,
    get_docker_service,
)
from app.main import app
from app.services.compose_service import ComposeInfo
from app.services.docker_service import ContainerInfo


def _authed_client():
    client = TestClient(app)
    client.post("/login", data={"username": "admin", "password": "admin"})
    return client


def test_favicon_is_served():
    resp = TestClient(app).get("/static/favicon.svg")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")


def test_dashboard_renders_containers_and_images_metric():
    mock_docker = MagicMock()
    mock_docker.list_containers.return_value = [
        ContainerInfo(id="1234567890ab", short_id="1234567890ab", name="jellyfin", image="jellyfin/jellyfin:latest", status="running")
    ]
    mock_docker.list_images.return_value = []

    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    try:
        resp = _authed_client().get("/")
        assert resp.status_code == 200
        assert "jellyfin" in resp.text
        assert "Compose Stacks" in resp.text
        assert "Imagens" in resp.text
        assert "Traefik Routes" not in resp.text
        assert 'href="/settings"' not in resp.text
        assert 'href="/docker"' in resp.text
        assert 'href="/static/favicon.svg"' in resp.text
    finally:
        app.dependency_overrides.clear()


def test_container_action_and_logs():
    mock_docker = MagicMock()
    mock_docker.list_containers.return_value = []
    mock_docker.get_logs.return_value = "Server started"

    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    try:
        client = _authed_client()
        resp = client.post("/containers/abc123/restart")
        assert resp.status_code == 200
        mock_docker.container_action.assert_called_once_with("abc123", "restart")

        resp_logs = client.get("/containers/abc123/logs")
        assert resp_logs.status_code == 200
        assert "Server started" in resp_logs.text
    finally:
        app.dependency_overrides.clear()


def test_get_container_compose():
    mock_compose = MagicMock()
    mock_compose.get_compose_info.return_value = ComposeInfo(
        container_id="c_123",
        container_name="my_web",
        stack_name="webstack",
        service_name="web",
        file_path=Path("/opt/stacks/webstack/compose.yaml"),
        compose_content="services:\n  web:\n    image: nginx:alpine\n",
        env_content="PORT=80\n",
        is_generated=False,
        exists_on_disk=True,
    )

    app.dependency_overrides[get_compose_service] = lambda: mock_compose
    try:
        client = _authed_client()
        resp = client.get("/containers/c_123/compose")
        assert resp.status_code == 200
        assert "webstack" in resp.text
        assert "image: nginx:alpine" in resp.text
        assert "PORT=80" in resp.text
        assert "Salvar" in resp.text
        assert "Salvar &amp; Aplicar" in resp.text or "Salvar & Aplicar" in resp.text
    finally:
        app.dependency_overrides.clear()


def test_save_container_compose():
    mock_compose = MagicMock()
    mock_compose.save_compose_file.return_value = Path("/opt/stacks/webstack/compose.yaml")
    mock_compose.get_compose_info.return_value = ComposeInfo(
        container_id="c_123",
        container_name="my_web",
        stack_name="webstack",
        service_name="web",
        file_path=Path("/opt/stacks/webstack/compose.yaml"),
        compose_content="services:\n  web:\n    image: nginx:alpine\n",
        env_content=None,
        is_generated=False,
        exists_on_disk=True,
    )

    app.dependency_overrides[get_compose_service] = lambda: mock_compose
    try:
        client = _authed_client()
        resp = client.post(
            "/containers/c_123/compose",
            data={
                "compose_content": "services:\n  web:\n    image: nginx:alpine\n",
                "env_content": "",
                "action": "save",
            },
        )
        assert resp.status_code == 200
        assert "Arquivo salvo com sucesso" in resp.text
        mock_compose.save_compose_file.assert_called_once()
    finally:
        app.dependency_overrides.clear()


def test_deploy_container_compose():
    mock_compose = MagicMock()
    mock_compose.deploy_compose.return_value = (True, "Container webstack-web-1 Started")
    mock_compose.get_compose_info.return_value = ComposeInfo(
        container_id="c_123",
        container_name="my_web",
        stack_name="webstack",
        service_name="web",
        file_path=Path("/opt/stacks/webstack/compose.yaml"),
        compose_content="services:\n  web:\n    image: nginx:alpine\n",
        env_content=None,
        is_generated=False,
        exists_on_disk=True,
    )

    app.dependency_overrides[get_compose_service] = lambda: mock_compose
    try:
        client = _authed_client()
        resp = client.post(
            "/containers/c_123/compose",
            data={
                "compose_content": "services:\n  web:\n    image: nginx:alpine\n",
                "env_content": "",
                "action": "deploy",
            },
        )
        assert resp.status_code == 200
        assert "Container webstack-web-1 Started" in resp.text
        assert "implantada com sucesso" in resp.text
        mock_compose.deploy_compose.assert_called_once()
    finally:
        app.dependency_overrides.clear()


def test_save_container_compose_invalid_yaml_returns_error():
    mock_compose = MagicMock()
    mock_compose.save_compose_file.side_effect = ValueError("Erro de sintaxe no YAML (linha 2)")
    mock_compose.get_compose_info.return_value = ComposeInfo(
        container_id="c_123",
        container_name="my_web",
        stack_name="webstack",
        service_name="web",
        file_path=Path("/opt/stacks/webstack/compose.yaml"),
        compose_content="bad: yaml: [",
        env_content=None,
        is_generated=False,
        exists_on_disk=True,
    )

    app.dependency_overrides[get_compose_service] = lambda: mock_compose
    try:
        client = _authed_client()
        resp = client.post(
            "/containers/c_123/compose",
            data={
                "compose_content": "bad: yaml: [",
                "env_content": "",
                "action": "save",
            },
        )
        assert resp.status_code == 200
        assert "Erro de sintaxe no YAML" in resp.text
    finally:
        app.dependency_overrides.clear()
