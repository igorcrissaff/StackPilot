from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.dependencies import (
    get_docker_service,
    get_metrics_collector,
    get_metrics_history,
    get_metrics_service,
    get_metrics_settings,
)
from app.main import app
from app.services.metrics_history import HistoryBucket
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


def test_metrics_rejects_invalid_multiplier():
    collector = MagicMock()
    collector.chart_series.return_value = {
        "labels": [], "cpu": [], "memory": [], "swap": [], "disk": [],
    }
    app.dependency_overrides[get_metrics_collector] = lambda: collector
    try:
        assert _client().get("/metrics?multiplier=15").status_code == 400
        assert _client().get("/metrics?multiplier=0").status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_metrics_includes_chart_payload():
    mock = MagicMock()
    mock.collect.return_value = _metrics()
    collector = MagicMock()
    collector.chart_series.return_value = {
        "labels": [1, 2],
        "cpu": [1.0, 2.0],
        "memory": [3.0, 4.0],
        "swap": [0.0, 0.0],
        "disk": [5.0, 6.0],
    }
    settings = MagicMock()
    settings.get_refresh_interval.return_value = 10
    app.dependency_overrides[get_metrics_service] = lambda: mock
    app.dependency_overrides[get_metrics_collector] = lambda: collector
    app.dependency_overrides[get_metrics_settings] = lambda: settings
    try:
        r = _client().get("/metrics?multiplier=10")
        assert r.status_code == 200
        assert 'id="metrics-chart-data"' in r.text
        assert 'id="metrics-window"' in r.text
        assert "every 10s" in r.text
        assert 'value="10" selected' in r.text
        assert 'id="metrics-chart-cpu"' not in r.text
        assert 'id="metrics-chart-memory"' not in r.text
        assert 'id="metrics-chart-disk"' not in r.text
    finally:
        app.dependency_overrides.clear()


def test_export_requires_auth():
    r = TestClient(app).get("/metrics/export.csv", follow_redirects=False)
    assert r.status_code == 303


def test_export_streams_csv():
    repo = MagicMock()
    repo.list_buckets.return_value = [
        HistoryBucket(
            bucket_start=300,
            cpu_percent=10.0,
            memory_percent=50.0,
            memory_used=1,
            memory_total=2,
            swap_percent=0.0,
            swap_used=0,
            swap_total=0,
            disk_percent=10.0,
            disk_used=1,
            disk_total=10,
            load_1=0.1,
            load_5=0.2,
            load_15=0.3,
            sample_count=30,
        )
    ]
    app.dependency_overrides[get_metrics_history] = lambda: repo
    try:
        r = _client().get("/metrics/export.csv?start=100&end=400")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]
        lines = r.text.strip().splitlines()
        assert lines[0].startswith("bucket_start,")
        assert "1970-01-01T00:05:00" in lines[1]
        repo.list_buckets.assert_called_once_with(100, 400)
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
        assert 'id="metrics-chart-cpu"' in r.text
        assert 'id="metrics-chart-memory"' in r.text
        assert 'id="metrics-chart-disk"' in r.text
        assert 'id="metrics-chart-swap"' in r.text
    finally:
        app.dependency_overrides.clear()
