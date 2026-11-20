from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.auth import require_auth
from app.dependencies import (
    get_metrics_collector,
    get_metrics_service,
    get_metrics_settings,
    templates,
)
from app.services.metrics_collector import MetricsCollector
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
