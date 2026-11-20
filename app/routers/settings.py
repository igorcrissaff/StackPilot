from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import require_auth
from app.dependencies import get_metrics_settings, templates
from app.services.metrics_settings import (
    DEFAULT_REFRESH_SECONDS,
    MAX_REFRESH_SECONDS,
    MIN_REFRESH_SECONDS,
    MetricsSettingsStore,
)

router = APIRouter(tags=["settings"])


def _current_interval(store: MetricsSettingsStore) -> int:
    try:
        return store.get_refresh_interval()
    except Exception:
        return DEFAULT_REFRESH_SECONDS


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    user: str = Depends(require_auth),
    store: MetricsSettingsStore = Depends(get_metrics_settings),
):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"interval": _current_interval(store), "message": None, "error": None},
    )


@router.post("/settings/metrics", response_class=HTMLResponse)
def update_metrics_settings(
    request: Request,
    interval: str = Form(...),
    user: str = Depends(require_auth),
    store: MetricsSettingsStore = Depends(get_metrics_settings),
):
    message = None
    error = None
    try:
        seconds = int(interval)
        store.set_refresh_interval(seconds)
        message = "Intervalo salvo."
    except (TypeError, ValueError):
        error = (
            f"O intervalo deve ser um número inteiro entre "
            f"{MIN_REFRESH_SECONDS} e {MAX_REFRESH_SECONDS} segundos."
        )

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request,
            "partials/metrics_settings.html",
            {"interval": _current_interval(store), "message": message, "error": error},
        )
    return RedirectResponse("/settings", status_code=303)
