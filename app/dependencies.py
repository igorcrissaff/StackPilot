import logging
import os
from pathlib import Path
from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.services.compose_service import ComposeService
from app.services.docker_service import DockerService
from app.services.dockerhub_service import DockerHubService
from app.services.hub_cache import HubCache
from app.services.metrics_collector import MetricsCollector
from app.services.metrics_history import MetricsHistoryRepository
from app.services.metrics_service import MetricsService
from app.services.metrics_settings import MetricsSettingsStore

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _resolve_db_path(configured: Path, fallback_name: str = "stackpilot.db") -> Path:
    parent = configured.parent
    if parent.is_dir() and os.access(parent, os.W_OK):
        return configured
    fallback = Path.cwd() / "data" / fallback_name
    fallback.parent.mkdir(parents=True, exist_ok=True)
    return fallback


def get_hub_cache() -> HubCache:
    return HubCache(_resolve_db_path(get_settings().hub_db_path))


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


def get_metrics_service() -> MetricsService:
    return MetricsService()


def get_metrics_history() -> MetricsHistoryRepository:
    return MetricsHistoryRepository(
        _resolve_db_path(get_settings().metrics_db_path, "metrics.db")
    )


def get_metrics_settings() -> MetricsSettingsStore:
    return MetricsSettingsStore(
        _resolve_db_path(get_settings().metrics_db_path, "metrics.db")
    )


def get_metrics_collector(request: Request) -> MetricsCollector:
    collector = getattr(request.app.state, "metrics_collector", None)
    if collector is None:
        collector = MetricsCollector(
            get_metrics_service(),
            get_metrics_history(),
            get_metrics_settings(),
        )
        request.app.state.metrics_collector = collector
    return collector


def get_compose_service() -> ComposeService:
    settings = get_settings()
    return ComposeService(
        docker_service=get_docker_service(),
        stacks_dir=settings.stacks_dir,
        compose_up_timeout=settings.compose_up_timeout_seconds,
        default_network=settings.stackpilot_network,
    )
