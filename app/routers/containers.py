from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from app.auth import require_auth
from app.dependencies import get_compose_service, get_docker_service, templates
from app.services.compose_service import ComposeService
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


@router.get("/{container_id}/compose", response_class=HTMLResponse)
def get_container_compose(
    request: Request,
    container_id: str,
    user: str = Depends(require_auth),
    compose_svc: ComposeService = Depends(get_compose_service),
):
    error = None
    info = None
    try:
        info = compose_svc.get_compose_info(container_id)
    except (ContainerNotFoundError, DockerUnavailableError, Exception) as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request,
        "partials/container_compose.html",
        {
            "container_id": container_id,
            "info": info,
            "error": error,
            "success": None,
            "output": None,
        },
    )


@router.post("/{container_id}/compose", response_class=HTMLResponse)
def save_or_deploy_container_compose(
    request: Request,
    container_id: str,
    compose_content: str = Form(...),
    env_content: str | None = Form(None),
    action: str = Form("save"),
    user: str = Depends(require_auth),
    compose_svc: ComposeService = Depends(get_compose_service),
):
    error = None
    success = None
    output = None
    info = None

    if action == "deploy":
        success_deploy, deploy_msg = compose_svc.deploy_compose(
            container_id=container_id,
            compose_content=compose_content,
            env_content=env_content,
        )
        if success_deploy:
            success = "Alterações salvas e stack implantada com sucesso!"
            output = deploy_msg
        else:
            error = deploy_msg
    else:
        try:
            saved_path = compose_svc.save_compose_file(
                container_id=container_id,
                compose_content=compose_content,
                env_content=env_content,
            )
            success = f"Arquivo salvo com sucesso em '{saved_path.name}'!"
        except ValueError as exc:
            error = str(exc)
        except Exception as exc:
            error = f"Erro ao salvar arquivo: {exc}"

    try:
        info = compose_svc.get_compose_info(container_id)
        if error:
            info.compose_content = compose_content
            info.env_content = env_content
    except Exception:
        pass

    return templates.TemplateResponse(
        request,
        "partials/container_compose.html",
        {
            "container_id": container_id,
            "info": info,
            "error": error,
            "success": success,
            "output": output,
        },
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
