from app.services.metrics_collector import MetricsCollector
from app.services.metrics_service import SystemMetrics

GB = 1024 ** 3


class FakeMetrics:
    def __init__(self, swap_total=0):
        self.cpu = 0.0
        self.swap_total = swap_total

    def collect(self):
        return SystemMetrics(
            cpu_percent=self.cpu,
            cpu_count=4,
            load_1=1.0,
            load_5=1.0,
            load_15=1.0,
            memory_used=GB,
            memory_total=4 * GB,
            memory_percent=25.0,
            swap_used=0,
            swap_total=self.swap_total,
            swap_percent=0.0,
            disk_used=GB,
            disk_total=10 * GB,
            disk_percent=10.0,
            uptime_seconds=100,
            os_name="Linux",
            os_version="1",
            kernel="k",
            architecture="x86_64",
            hostname="h",
        )


class FakeHistory:
    def __init__(self):
        self.rows = []

    def upsert_bucket(self, bucket):
        self.rows.append(bucket)


class FakeSettings:
    def __init__(self, interval=10):
        self.interval = interval

    def get_refresh_interval(self):
        return self.interval


def _collector(interval=10):
    return MetricsCollector(FakeMetrics(), FakeHistory(), FakeSettings(interval))


def test_flush_on_bucket_change_averages_samples():
    c = _collector()
    svc = FakeMetrics()
    for cpu, t in [(10.0, 0.0), (20.0, 10.0), (30.0, 300.0)]:
        svc.cpu = cpu
        c.record(svc.collect(), now=1000.0 + t)
    assert len(c.history.rows) == 1
    assert c.history.rows[0].bucket_start == 900
    assert c.history.rows[0].sample_count == 2
    assert abs(c.history.rows[0].cpu_percent - 15.0) < 1e-9


def test_buffer_prunes_to_100_intervals():
    c = _collector(interval=5)
    svc = FakeMetrics()
    base = 1000.0
    for i in range(300):
        c.record(svc.collect(), now=base + i)
    oldest = min(s.timestamp for s in c._buffer)
    assert oldest >= (base + 299) - 100 * 5


def test_chart_series_has_multiplier_points():
    c = _collector(interval=10)
    svc = FakeMetrics()
    now = 10_000.0
    for i in range(40):
        svc.cpu = float(i)
        c.record(svc.collect(), now=now - i * 10)
    data = c.chart_series(10, 10, now=now)
    assert len(data["labels"]) == 10
    assert len(data["cpu"]) == 10
    assert data["swap"] == [None] * 10
    assert data["swap_total"] == 0
    assert data["cpu"][-1] is not None


def test_chart_series_keeps_swap_when_present():
    c = _collector(interval=10)
    svc = FakeMetrics(swap_total=1024)
    now = 10_000.0
    for i in range(11):
        c.record(svc.collect(), now=now - i * 10)
    data = c.chart_series(10, 10, now=now)
    assert data["swap_total"] == 1024
    assert data["swap"] == [0.0] * 10


def test_concurrent_record_and_chart_does_not_error():
    import threading

    c = _collector(interval=5)
    svc = FakeMetrics()
    stop = threading.Event()

    def producer():
        i = 0
        while not stop.is_set():
            c.record(svc.collect(), now=float(1000 + i))
            i += 1

    thread = threading.Thread(target=producer)
    thread.start()
    try:
        for _ in range(200):
            c.chart_series(10, 5, now=1500.0)
    finally:
        stop.set()
        thread.join()
