import logging

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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

INVALID_HOSTNAME_MESSAGE = "Hostname inválido. Use um domínio simples, ex.: home.arpa"
DB_ERROR_MESSAGE = (
    "Não foi possível ler as configurações; usando o padrão do ambiente."
)
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
    try:
        current = settings_svc.get_base_domain(default)
        is_custom = settings_svc.get(GLOBAL_SCOPE, BASE_DOMAIN_KEY) is not None
    except Exception:
        logger.warning("settings store unavailable; rendering defaults", exc_info=True)
        current = default
        is_custom = False
        error = error or DB_ERROR_MESSAGE
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
    try:
        previous = settings_svc.get(GLOBAL_SCOPE, BASE_DOMAIN_KEY)
        old = settings_svc.get_base_domain(default)
    except Exception:
        logger.warning("settings store unavailable on save", exc_info=True)
        return _render_form(request, settings_svc, error=DB_ERROR_MESSAGE)

    try:
        new = settings_svc.set_base_domain(base_domain)
    except ValueError:
        return _render_form(request, settings_svc, error=INVALID_HOSTNAME_MESSAGE)
    except Exception:
        logger.warning("could not persist base domain", exc_info=True)
        return _render_form(request, settings_svc, error=DB_ERROR_MESSAGE)

    try:
        if new != old:
            traefik_svc.rewrite_base_domain(old, new)
    except Exception:
        logger.warning("could not migrate routes to new base domain", exc_info=True)
        try:
            _restore_override(settings_svc, previous)
        except Exception:
            logger.warning("could not restore previous override", exc_info=True)
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
    try:
        old = settings_svc.get_base_domain(default)
    except Exception:
        logger.warning("settings store unavailable on reset", exc_info=True)
        return _render_form(request, settings_svc, error=DB_ERROR_MESSAGE)

    try:
        settings_svc.reset_base_domain()
        if old != default:
            traefik_svc.rewrite_base_domain(old, default)
    except Exception:
        logger.warning("could not reset base domain", exc_info=True)
        try:
            settings_svc.set_base_domain(old)
        except Exception:
            logger.warning("could not restore override after reset", exc_info=True)
        return _render_form(request, settings_svc, error=RESET_ERROR_MESSAGE)

    return _render_form(request, settings_svc, message="Padrão do ambiente restaurado")
