import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import metrics_service
from app.services.metrics_service import MetricsService

GB = 1024 ** 3


def _fake_psutil():
    fake = MagicMock()
    fake.cpu_percent.return_value = 12.5
    fake.cpu_count.return_value = 8
    fake.getloadavg.return_value = (0.5, 0.4, 0.3)
    fake.virtual_memory.return_value = SimpleNamespace(used=2 * GB, total=8 * GB, percent=25.0)
    fake.swap_memory.return_value = SimpleNamespace(used=0, total=0, percent=0.0)
    fake.disk_usage.return_value = SimpleNamespace(used=100 * GB, total=500 * GB, percent=20.0)
    fake.boot_time.return_value = time.time() - 3600
    return fake


def test_collect_builds_metrics(monkeypatch):
    fake = _fake_psutil()
    monkeypatch.setattr(metrics_service, "psutil", fake)
    monkeypatch.setattr(metrics_service, "_read_os_release", lambda: ("Ubuntu 24.04", "24.04"))
    monkeypatch.setattr(metrics_service.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(metrics_service.platform, "release", lambda: "6.8.0")
    monkeypatch.setattr(metrics_service.platform, "system", lambda: "Linux")
    monkeypatch.setattr(metrics_service.socket, "gethostname", lambda: "homelab")

    m = MetricsService().collect()

    assert m.cpu_percent == 12.5
    assert m.cpu_count == 8
    assert m.load_1 == 0.5
    assert m.load_5 == 0.4
    assert m.load_15 == 0.3
    assert m.memory_total == 8 * GB
    assert m.memory_percent == 25.0
    assert m.disk_percent == 20.0
    assert 3590 <= m.uptime_seconds <= 3610
    assert m.os_name == "Ubuntu 24.04"
    assert m.os_version == "24.04"
    assert m.kernel == "6.8.0"
    assert m.architecture == "x86_64"
    assert m.hostname == "homelab"


def test_collect_handles_missing_loadavg(monkeypatch):
    fake = _fake_psutil()
    fake.getloadavg.side_effect = OSError("not supported")
    monkeypatch.setattr(metrics_service, "psutil", fake)
    monkeypatch.setattr(metrics_service, "_read_os_release", lambda: (None, None))
    monkeypatch.setattr(metrics_service.platform, "system", lambda: "Windows")
    monkeypatch.setattr(metrics_service.platform, "release", lambda: "11")
    monkeypatch.setattr(metrics_service.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(metrics_service.socket, "gethostname", lambda: "pc")

    m = MetricsService().collect()

    assert m.load_1 is None and m.load_5 is None and m.load_15 is None
    assert m.os_name == "Windows"
    assert m.os_version == "11"


def test_read_os_release_fallback_when_missing(monkeypatch, tmp_path):
    missing = tmp_path / "os-release"
    monkeypatch.setattr(metrics_service, "OS_RELEASE_PATH", missing)
    assert metrics_service._read_os_release() == (None, None)
