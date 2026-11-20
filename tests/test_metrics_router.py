from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.dependencies import get_docker_service, get_metrics_service
from app.main import app
from app.services.metrics_service import SystemMetrics


def _client():
    c = TestClient(app)
    c.post("/login", data={"username": "admin", "password": "admin"})
    return c


def _metrics(hostname="homelab"):
    return SystemMetrics(
        cpu_percent=12.5,
        cpu_count=8,
        load_1=0.5,
        load_5=0.4,
        load_15=0.3,
        memory_used=2 * 1024 ** 3,
        memory_total=8 * 1024 ** 3,
        memory_percent=25.0,
        swap_used=0,
        swap_total=0,
        swap_percent=0.0,
        disk_used=100 * 1024 ** 3,
        disk_total=500 * 1024 ** 3,
        disk_percent=20.0,
        uptime_seconds=3600,
        os_name="Ubuntu 24.04",
        os_version="24.04",
        kernel="6.8.0",
        architecture="x86_64",
        hostname=hostname,
    )


def test_metrics_requires_auth():
    r = TestClient(app).get("/metrics", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_metrics_renders_host_data():
    mock = MagicMock()
    mock.collect.return_value = _metrics()
    app.dependency_overrides[get_metrics_service] = lambda: mock
    try:
        r = _client().get("/metrics")
        assert r.status_code == 200
        assert "homelab" in r.text
        assert "Ubuntu 24.04" in r.text
        assert "12.5" in r.text
        assert 'hx-get="/metrics"' in r.text
        assert "every 10s" in r.text
    finally:
        app.dependency_overrides.clear()


def test_dashboard_includes_metrics_section():
    mock_docker = MagicMock()
    mock_docker.list_containers.return_value = []
    mock_docker.list_images.return_value = []
    mock_metrics = MagicMock()
    mock_metrics.collect.return_value = _metrics()
    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    app.dependency_overrides[get_metrics_service] = lambda: mock_metrics
    try:
        r = _client().get("/")
        assert r.status_code == 200
        assert 'id="system-metrics"' in r.text
        assert 'hx-get="/metrics"' in r.text
    finally:
        app.dependency_overrides.clear()
