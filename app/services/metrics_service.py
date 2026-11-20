import platform
import socket
import time
from pathlib import Path

import psutil
from pydantic import BaseModel

OS_RELEASE_PATH = Path("/etc/os-release")


class SystemMetrics(BaseModel):
    cpu_percent: float
    cpu_count: int
    load_1: float | None
    load_5: float | None
    load_15: float | None
    memory_used: int
    memory_total: int
    memory_percent: float
    swap_used: int
    swap_total: int
    swap_percent: float
    disk_used: int
    disk_total: int
    disk_percent: float
    uptime_seconds: int
    os_name: str
    os_version: str
    kernel: str
    architecture: str
    hostname: str


def _read_os_release() -> tuple[str | None, str | None]:
    try:
        text = OS_RELEASE_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return (None, None)

    data: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")

    name = data.get("PRETTY_NAME") or data.get("NAME")
    version = data.get("VERSION_ID") or data.get("VERSION")
    return (name, version)


def _load_avg() -> tuple[float | None, float | None, float | None]:
    try:
        one, five, fifteen = psutil.getloadavg()
    except (OSError, AttributeError):
        return (None, None, None)
    return (one, five, fifteen)


class MetricsService:
    def collect(self) -> SystemMetrics:
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage("/")
        load_1, load_5, load_15 = _load_avg()
        os_name, os_version = _read_os_release()

        return SystemMetrics(
            cpu_percent=float(psutil.cpu_percent(interval=0.1)),
            cpu_count=int(psutil.cpu_count() or 0),
            load_1=load_1,
            load_5=load_5,
            load_15=load_15,
            memory_used=int(memory.used),
            memory_total=int(memory.total),
            memory_percent=float(memory.percent),
            swap_used=int(swap.used),
            swap_total=int(swap.total),
            swap_percent=float(swap.percent),
            disk_used=int(disk.used),
            disk_total=int(disk.total),
            disk_percent=float(disk.percent),
            uptime_seconds=max(0, int(time.time() - psutil.boot_time())),
            os_name=os_name or platform.system(),
            os_version=os_version or platform.release(),
            kernel=platform.release(),
            architecture=platform.machine(),
            hostname=socket.gethostname(),
        )
