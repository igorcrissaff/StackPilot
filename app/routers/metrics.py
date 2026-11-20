from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.auth import require_auth
from app.dependencies import get_metrics_service, templates
from app.services.metrics_service import MetricsService

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=HTMLResponse)
def system_metrics(
    request: Request,
    user: str = Depends(require_auth),
    metrics_svc: MetricsService = Depends(get_metrics_service),
):
    metrics = None
    error = None
    try:
        metrics = metrics_svc.collect()
    except Exception as exc:
        error = f"Não foi possível coletar métricas: {exc}"
    return templates.TemplateResponse(
        request,
        "partials/system_metrics.html",
        {"metrics": metrics, "error": error},
    )
