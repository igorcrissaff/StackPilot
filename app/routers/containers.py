from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.auth import require_auth
from app.dependencies import get_docker_service, templates
from app.services.docker_service import (
    ContainerNotFoundError,
    DockerService,
    DockerUnavailableError,
)

router = APIRouter(prefix="/containers", tags=["containers"])


@router.get("", response_class=HTMLResponse)
def list_containers(
    request: Request,
    user: str = Depends(require_auth),
    docker_svc: DockerService = Depends(get_docker_service),
):
    error = None
    containers = []
    try:
        containers = docker_svc.list_containers()
    except DockerUnavailableError as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request,
        "partials/container_list.html",
        {"containers": containers, "error": error},
    )


@router.post("/{container_id}/{action}", response_class=HTMLResponse)
def container_action(
    request: Request,
    container_id: str,
    action: str,
    user: str = Depends(require_auth),
    docker_svc: DockerService = Depends(get_docker_service),
):
    error = None
    containers = []
    try:
        docker_svc.container_action(container_id, action)
        containers = docker_svc.list_containers()
    except (ContainerNotFoundError, DockerUnavailableError, ValueError) as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request,
        "partials/container_list.html",
        {"containers": containers, "error": error},
    )


@router.get("/{container_id}/logs", response_class=HTMLResponse)
def container_logs(
    request: Request,
    container_id: str,
    user: str = Depends(require_auth),
    docker_svc: DockerService = Depends(get_docker_service),
):
    error = None
    logs = ""
    try:
        logs = docker_svc.get_logs(container_id)
    except (ContainerNotFoundError, DockerUnavailableError) as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request,
        "partials/container_logs.html",
        {"container_id": container_id, "logs": logs, "error": error},
    )
