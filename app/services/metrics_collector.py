from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass

from app.services.metrics_history import HistoryBucket
from app.services.metrics_service import SystemMetrics

logger = logging.getLogger(__name__)

BUCKET_SECONDS = 300
MAX_WINDOW_MULTIPLIER = 100


@dataclass
class RecentSample:
    timestamp: float
    cpu_percent: float
    memory_percent: float
    swap_percent: float
    swap_total: int
    disk_percent: float


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _mean_optional(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


class MetricsCollector:
    def __init__(self, metrics_service, history, settings, sample_interval: int = 10):
        self.metrics_service = metrics_service
        self.history = history
        self.settings = settings
        self.sample_interval = sample_interval
        self._buffer: deque[RecentSample] = deque()
        self._lock = threading.RLock()
        self._accumulator: list[SystemMetrics] = []
        self._bucket_start: int | None = None
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

    def record(self, metrics: SystemMetrics, now: float | None = None) -> None:
        with self._lock:
            moment = time.time() if now is None else now
            bucket_start = int(moment) - int(moment) % BUCKET_SECONDS

            if self._bucket_start is None:
                self._bucket_start = bucket_start
            elif bucket_start != self._bucket_start:
                self.flush()
                self._bucket_start = bucket_start

            self._buffer.append(
                RecentSample(
                    timestamp=moment,
                    cpu_percent=metrics.cpu_percent,
                    memory_percent=metrics.memory_percent,
                    swap_percent=metrics.swap_percent,
                    swap_total=metrics.swap_total,
                    disk_percent=metrics.disk_percent,
                )
            )
            self._accumulator.append(metrics)

            cutoff = moment - MAX_WINDOW_MULTIPLIER * self.settings.get_refresh_interval()
            while self._buffer and self._buffer[0].timestamp < cutoff:
                self._buffer.popleft()

    def flush(self) -> None:
        with self._lock:
            if not self._accumulator or self._bucket_start is None:
                return

            samples = self._accumulator
            count = len(samples)
            bucket = HistoryBucket(
                bucket_start=self._bucket_start,
                cpu_percent=_mean([s.cpu_percent for s in samples]),
                memory_percent=_mean([s.memory_percent for s in samples]),
                memory_used=int(round(_mean([s.memory_used for s in samples]))),
                memory_total=int(round(_mean([s.memory_total for s in samples]))),
                swap_percent=_mean([s.swap_percent for s in samples]),
                swap_used=int(round(_mean([s.swap_used for s in samples]))),
                swap_total=int(round(_mean([s.swap_total for s in samples]))),
                disk_percent=_mean([s.disk_percent for s in samples]),
                disk_used=int(round(_mean([s.disk_used for s in samples]))),
                disk_total=int(round(_mean([s.disk_total for s in samples]))),
                load_1=_mean_optional([s.load_1 for s in samples]),
                load_5=_mean_optional([s.load_5 for s in samples]),
                load_15=_mean_optional([s.load_15 for s in samples]),
                sample_count=count,
            )
            self.history.upsert_bucket(bucket)
            self._accumulator = []

    def chart_series(
        self, multiplier: int, interval: int, now: float | None = None
    ) -> dict[str, list]:
        with self._lock:
            moment = time.time() if now is None else now
            window = multiplier * interval
            cutoff = moment - window
            labels = [int(cutoff + index * interval) for index in range(multiplier)]

            keys = ("cpu", "memory", "swap", "disk")
            sums: dict[str, list[float]] = {key: [0.0] * multiplier for key in keys}
            counts = [0] * multiplier
            swap_total = self._buffer[-1].swap_total if self._buffer else 0

            for sample in self._buffer:
                if sample.timestamp < cutoff or sample.timestamp > moment:
                    continue
                index = int((sample.timestamp - cutoff) // interval)
                index = min(max(index, 0), multiplier - 1)
                sums["cpu"][index] += sample.cpu_percent
                sums["memory"][index] += sample.memory_percent
                sums["swap"][index] += sample.swap_percent
                sums["disk"][index] += sample.disk_percent
                counts[index] += 1

            result: dict[str, list] = {"labels": labels, "swap_total": swap_total}
            for key in keys:
                result[key] = [
                    (sums[key][index] / counts[index]) if counts[index] else None
                    for index in range(multiplier)
                ]
            if swap_total <= 0:
                result["swap"] = [None] * multiplier
            return result

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while self._stop_event is not None and not self._stop_event.is_set():
            interval = self.settings.get_refresh_interval()
            sleep_for = min(self.sample_interval, interval)
            try:
                metrics = await asyncio.to_thread(self.metrics_service.collect)
                self.record(metrics)
            except Exception:
                logger.exception("Failed to collect host metrics")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_for)
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.flush()
