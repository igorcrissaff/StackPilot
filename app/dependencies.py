import logging
import os
from pathlib import Path
from fastapi import Depends
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.services.compose_service import ComposeService
from app.services.docker_service import DockerService
from app.services.dockerhub_service import DockerHubService
from app.services.hub_cache import HubCache
from app.services.settings_service import SettingsService
from app.services.traefik_service import TraefikService

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _resolve_db_path(configured: Path) -> Path:
    parent = configured.parent
    if parent.is_dir() and os.access(parent, os.W_OK):
        return configured
    fallback = Path.cwd() / "data" / "stackpilot.db"
    fallback.parent.mkdir(parents=True, exist_ok=True)
    return fallback


def get_hub_cache() -> HubCache:
    return HubCache(_resolve_db_path(get_settings().hub_db_path))


def get_settings_service() -> SettingsService:
    return SettingsService(_resolve_db_path(get_settings().hub_db_path))


def get_effective_base_domain() -> str:
    default = get_settings().base_domain
    try:
        return get_settings_service().get_base_domain(default)
    except Exception:
        logger.warning(
            "settings store unavailable; falling back to BASE_DOMAIN",
            exc_info=True,
        )
        return default


def get_dockerhub_service() -> DockerHubService:
    settings = get_settings()
    return DockerHubService(
        cache=get_hub_cache(),
        ttl_seconds=settings.hub_cache_ttl_seconds,
        api_base=settings.hub_api_base,
        timeout=settings.hub_request_timeout_seconds,
    )


def get_docker_service() -> DockerService:
    return DockerService()


def get_traefik_service(
    base_domain: str = Depends(get_effective_base_domain),
) -> TraefikService:
    settings = get_settings()
    return TraefikService(
        dynamic_dir=settings.traefik_dynamic_dir,
        base_domain=base_domain,
    )


def get_compose_service() -> ComposeService:
    settings = get_settings()
    return ComposeService(
        docker_service=get_docker_service(),
        stacks_dir=settings.stacks_dir,
        compose_up_timeout=settings.compose_up_timeout_seconds,
        default_network=settings.stackpilot_network,
    )
