from pathlib import Path
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.services.docker_service import DockerService
from app.services.traefik_service import TraefikService

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def get_docker_service() -> DockerService:
    return DockerService()


def get_traefik_service() -> TraefikService:
    return TraefikService(dynamic_dir=get_settings().traefik_dynamic_dir)
