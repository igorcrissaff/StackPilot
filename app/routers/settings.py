from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from app.auth import require_auth
from app.config import get_settings
from app.dependencies import get_settings_service, get_traefik_service, templates
from app.services.settings_service import (
    BASE_DOMAIN_KEY,
    GLOBAL_SCOPE,
    SettingsService,
)
from app.services.traefik_service import TraefikService

router = APIRouter(prefix="/settings", tags=["settings"])

INVALID_HOSTNAME_MESSAGE = "Hostname inválido. Use um domínio simples, ex.: home.arpa"
MIGRATION_ERROR_MESSAGE = (
    "Não foi possível atualizar as rotas; configuração anterior mantida."
)
RESET_ERROR_MESSAGE = (
    "Não foi possível restaurar o padrão; configuração anterior mantida."
)


def _form_context(
    settings_svc: SettingsService,
    message: str | None = None,
    error: str | None = None,
) -> dict:
    default = get_settings().base_domain
    current = settings_svc.get_base_domain(default)
    is_custom = settings_svc.get(GLOBAL_SCOPE, BASE_DOMAIN_KEY) is not None
    return {
        "base_domain": current,
        "default_base_domain": default,
        "is_custom": is_custom,
        "message": message,
        "error": error,
    }


def _render_form(
    request: Request,
    settings_svc: SettingsService,
    message: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/settings_general_form.html",
        _form_context(settings_svc, message=message, error=error),
    )


def _restore_override(settings_svc: SettingsService, previous: str | None) -> None:
    if previous is None:
        settings_svc.reset_base_domain()
    else:
        settings_svc.set(GLOBAL_SCOPE, BASE_DOMAIN_KEY, previous)


@router.get("", response_class=HTMLResponse)
def settings_page(
    request: Request,
    user: str = Depends(require_auth),
    settings_svc: SettingsService = Depends(get_settings_service),
):
    context = _form_context(settings_svc)
    context["user"] = user
    return templates.TemplateResponse(request, "settings.html", context)


@router.post("", response_class=HTMLResponse)
def update_settings(
    request: Request,
    base_domain: str = Form(...),
    user: str = Depends(require_auth),
    settings_svc: SettingsService = Depends(get_settings_service),
    traefik_svc: TraefikService = Depends(get_traefik_service),
):
    default = get_settings().base_domain
    previous = settings_svc.get(GLOBAL_SCOPE, BASE_DOMAIN_KEY)
    old = settings_svc.get_base_domain(default)

    try:
        new = settings_svc.set_base_domain(base_domain)
    except ValueError:
        return _render_form(request, settings_svc, error=INVALID_HOSTNAME_MESSAGE)

    try:
        if new != old:
            traefik_svc.rewrite_base_domain(old, new)
    except Exception:
        _restore_override(settings_svc, previous)
        return _render_form(request, settings_svc, error=MIGRATION_ERROR_MESSAGE)

    return _render_form(request, settings_svc, message="Configurações salvas")


@router.post("/reset", response_class=HTMLResponse)
def reset_settings(
    request: Request,
    user: str = Depends(require_auth),
    settings_svc: SettingsService = Depends(get_settings_service),
    traefik_svc: TraefikService = Depends(get_traefik_service),
):
    default = get_settings().base_domain
    old = settings_svc.get_base_domain(default)

    try:
        settings_svc.reset_base_domain()
        if old != default:
            traefik_svc.rewrite_base_domain(old, default)
    except Exception:
        settings_svc.set_base_domain(old)
        return _render_form(request, settings_svc, error=RESET_ERROR_MESSAGE)

    return _render_form(request, settings_svc, message="Padrão do ambiente restaurado")
