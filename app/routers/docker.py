from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.auth import require_auth
from app.dependencies import (
    get_docker_service,
    get_dockerhub_service,
    get_hub_cache,
    templates,
)
from app.services.docker_service import DockerService, DockerUnavailableError
from app.services.dockerhub_service import (
    DockerHubService,
    HubUnavailableError,
    InvalidImageReferenceError,
)
from app.services.hub_cache import HubCache

router = APIRouter(tags=["docker"])


def _load_images(docker_svc: DockerService, hub_cache: HubCache):
    images = []
    used_images = []
    images_error = None
    try:
        images = docker_svc.list_images()
    except DockerUnavailableError as exc:
        images_error = str(exc)
    try:
        used_images = hub_cache.list_used_images()
    except Exception as exc:
        if not images_error:
            images_error = f"Não foi possível ler o cache local: {exc}"
    return images, used_images, images_error


@router.get("/docker", response_class=HTMLResponse)
def docker_page(
    request: Request,
    user: str = Depends(require_auth),
    docker_svc: DockerService = Depends(get_docker_service),
    hub_cache: HubCache = Depends(get_hub_cache),
):
    images, used_images, images_error = _load_images(docker_svc, hub_cache)
    containers = []
    containers_error = None
    try:
        containers = docker_svc.list_containers()
    except DockerUnavailableError as exc:
        containers_error = str(exc)
    return templates.TemplateResponse(
        request,
        "docker.html",
        {
            "user": user,
            "images": images,
            "used_images": used_images,
            "images_error": images_error,
            "containers": containers,
            "containers_error": containers_error,
        },
    )


@router.get("/docker/images", response_class=HTMLResponse)
def docker_images(
    request: Request,
    user: str = Depends(require_auth),
    docker_svc: DockerService = Depends(get_docker_service),
    hub_cache: HubCache = Depends(get_hub_cache),
):
    images, used_images, images_error = _load_images(docker_svc, hub_cache)
    return templates.TemplateResponse(
        request,
        "partials/image_list.html",
        {
            "images": images,
            "used_images": used_images,
            "images_error": images_error,
        },
    )

@router.get("/hub/search", response_class=HTMLResponse)
def hub_search(
    request: Request,
    q: str = "",
    user: str = Depends(require_auth),
    hub_svc: DockerHubService = Depends(get_dockerhub_service),
):
    query = q.strip()
    results = None
    error = None
    if query:
        try:
            results = hub_svc.search_images(query)
        except HubUnavailableError as exc:
            error = str(exc)
    return templates.TemplateResponse(
        request,
        "partials/hub_search.html",
        {"query": query, "results": results, "error": error},
    )


@router.get("/hub/tags", response_class=HTMLResponse)
def hub_tags(
    request: Request,
    repo: str = "",
    user: str = Depends(require_auth),
    hub_svc: DockerHubService = Depends(get_dockerhub_service),
):
    repo_name = repo.strip()
    result = None
    error = None
    if repo_name:
        try:
            result = hub_svc.list_tags(repo_name)
        except (HubUnavailableError, InvalidImageReferenceError) as exc:
            error = str(exc)
    return templates.TemplateResponse(
        request,
        "partials/hub_tags.html",
        {"repo": repo_name, "result": result, "error": error},
    )
