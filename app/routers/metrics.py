import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from app.auth import require_auth
from app.dependencies import (
    get_metrics_collector,
    get_metrics_history,
    get_metrics_service,
    get_metrics_settings,
    templates,
)
from app.services.metrics_collector import MetricsCollector
from app.services.metrics_history import MetricsHistoryRepository
from app.services.metrics_service import MetricsService
from app.services.metrics_settings import DEFAULT_REFRESH_SECONDS, MetricsSettingsStore

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=HTMLResponse)
def system_metrics(
    request: Request,
    multiplier: int = 30,
    user: str = Depends(require_auth),
    metrics_svc: MetricsService = Depends(get_metrics_service),
    collector: MetricsCollector = Depends(get_metrics_collector),
    metrics_settings: MetricsSettingsStore = Depends(get_metrics_settings),
):
    if multiplier < 10 or multiplier > 100 or multiplier % 10 != 0:
        raise HTTPException(status_code=400, detail="multiplier must be 10..100 step 10")

    try:
        interval = metrics_settings.get_refresh_interval()
    except Exception:
        interval = DEFAULT_REFRESH_SECONDS

    metrics = None
    error = None
    try:
        metrics = metrics_svc.collect()
    except Exception as exc:
        error = f"Não foi possível coletar métricas: {exc}"

    chart = collector.chart_series(multiplier, interval)

    return templates.TemplateResponse(
        request,
        "partials/system_metrics.html",
        {
            "metrics": metrics,
            "error": error,
            "chart": chart,
            "interval": interval,
            "multiplier": multiplier,
            "multipliers": list(range(10, 101, 10)),
        },
    )


_COLUMNS = [
    "bucket_start",
    "cpu_percent",
    "memory_percent",
    "memory_used",
    "memory_total",
    "swap_percent",
    "swap_used",
    "swap_total",
    "disk_percent",
    "disk_used",
    "disk_total",
    "load_1",
    "load_5",
    "load_15",
    "sample_count",
]


def _parse_timestamp(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="start/end must be epoch seconds")


@router.get("/metrics/export.csv")
def export_metrics(
    start: str | None = None,
    end: str | None = None,
    user: str = Depends(require_auth),
    history: MetricsHistoryRepository = Depends(get_metrics_history),
):
    start_value = _parse_timestamp(start)
    end_value = _parse_timestamp(end)
    rows = history.list_buckets(start_value, end_value)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_COLUMNS)
    for bucket in rows:
        writer.writerow(
            [
                datetime.fromtimestamp(bucket.bucket_start, tz=timezone.utc).isoformat(),
                bucket.cpu_percent,
                bucket.memory_percent,
                bucket.memory_used,
                bucket.memory_total,
                bucket.swap_percent,
                bucket.swap_used,
                bucket.swap_total,
                bucket.disk_percent,
                bucket.disk_used,
                bucket.disk_total,
                bucket.load_1,
                bucket.load_5,
                bucket.load_15,
                bucket.sample_count,
            ]
        )

    filename = f"stackpilot-metrics-{datetime.now(timezone.utc):%Y%m%d}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
