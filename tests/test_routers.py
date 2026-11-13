from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app, get_docker_service, get_traefik_service
from app.services.docker_service import ContainerInfo
from app.services.traefik_service import RouteConfig


def _authed_client():
    client = TestClient(app)
    client.post("/login", data={"username": "admin", "password": "admin"})
    return client


def test_dashboard_renders_containers_and_routes():
    mock_docker = MagicMock()
    mock_docker.list_containers.return_value = [
        ContainerInfo(id="1234567890ab", short_id="1234567890ab", name="jellyfin", image="jellyfin/jellyfin:latest", status="running")
    ]
    mock_traefik = MagicMock()
    mock_traefik.list_routes.return_value = [
        RouteConfig(name="jellyfin", domain="jellyfin.home.arpa", target_url="http://jellyfin:8096", tls=True)
    ]

    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    app.dependency_overrides[get_traefik_service] = lambda: mock_traefik
    try:
        client = _authed_client()
        resp = client.get("/")
        assert resp.status_code == 200
        assert "jellyfin" in resp.text
        assert "jellyfin.home.arpa" in resp.text
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


def test_create_and_delete_route():
    mock_traefik = MagicMock()
    mock_traefik.list_routes.return_value = []
    mock_traefik.delete_route.return_value = True

    app.dependency_overrides[get_traefik_service] = lambda: mock_traefik
    try:
        client = _authed_client()
        resp = client.post(
            "/routes",
            data={"name": "plex", "domain": "plex.home.arpa", "target_url": "http://plex:32400", "tls": "on"},
        )
        assert resp.status_code == 200
        mock_traefik.upsert_route.assert_called_once()

        resp_del = client.delete("/routes/plex")
        assert resp_del.status_code == 200
        mock_traefik.delete_route.assert_called_once_with("plex")
    finally:
        app.dependency_overrides.clear()
