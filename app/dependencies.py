from pathlib import Path
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.services.compose_service import ComposeService
from app.services.docker_service import DockerService
from app.services.traefik_service import TraefikService

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def get_docker_service() -> DockerService:
    return DockerService()


def get_traefik_service() -> TraefikService:
    settings = get_settings()
    return TraefikService(
        dynamic_dir=settings.traefik_dynamic_dir,
        base_domain=settings.base_domain,
    )


def get_compose_service() -> ComposeService:
    settings = get_settings()
    return ComposeService(
        docker_service=get_docker_service(),
        stacks_dir=settings.stacks_dir,
    )
