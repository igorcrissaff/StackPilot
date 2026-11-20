from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from app.auth import require_auth
from app.dependencies import (
    get_compose_service,
    get_docker_service,
    get_dockerhub_service,
    get_hub_cache,
    get_task_service,
    templates,
)
from app.services.compose_service import ComposeService
from app.services.docker_service import (
    DockerService,
    DockerUnavailableError,
    ImageInUseError,
    ImageNotFoundError,
    ImagePullError,
)
from app.services.dockerhub_service import (
    DockerHubService,
    HubUnavailableError,
    InvalidImageReferenceError,
)
from app.services.hub_cache import HubCache
from app.services.task_service import TaskService

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

def _render_images(
    request: Request,
    docker_svc: DockerService,
    hub_cache: HubCache,
    message: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    images, used_images, images_error = _load_images(docker_svc, hub_cache)
    return templates.TemplateResponse(
        request,
        "partials/image_list.html",
        {
            "images": images,
            "used_images": used_images,
            "images_error": images_error,
            "message": message,
            "error": error,
        },
    )


@router.post("/docker/images/remove", response_class=HTMLResponse)
async def remove_image(
    request: Request,
    image: str = Form(...),
    force: bool = Form(False),
    user: str = Depends(require_auth),
    docker_svc: DockerService = Depends(get_docker_service),
    hub_cache: HubCache = Depends(get_hub_cache),
    task_svc: TaskService = Depends(get_task_service),
):
    ref = image.strip()
    task_svc.enqueue(
        f"Remover imagem {ref}",
        lambda: docker_svc.remove_image(ref, force=force),
    )
    message = f"Remoção da imagem {ref} iniciada em segundo plano."
    return _render_images(request, docker_svc, hub_cache, message=message, error=None)


@router.post("/docker/images/pull", response_class=HTMLResponse)
async def pull_image(
    request: Request,
    image: str = Form(...),
    user: str = Depends(require_auth),
    docker_svc: DockerService = Depends(get_docker_service),
    hub_cache: HubCache = Depends(get_hub_cache),
    task_svc: TaskService = Depends(get_task_service),
):
    ref = image.strip()
    task_svc.enqueue(
        f"Pull da imagem {ref}",
        lambda: docker_svc.pull_image(ref),
    )
    message = f"Pull da imagem {ref} iniciado em segundo plano."
    return _render_images(request, docker_svc, hub_cache, message=message, error=None)


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


@router.get("/docker/compose", response_class=HTMLResponse)
def compose_editor(
    request: Request,
    image: str = "",
    user: str = Depends(require_auth),
    compose_svc: ComposeService = Depends(get_compose_service),
):
    image_ref = image.strip()
    compose_content = ""
    stack_name = ""
    error = None
    if image_ref:
        compose_content = compose_svc.generate_starter_compose(image_ref)
        stack_name = compose_svc.derive_service_name(image_ref)
    else:
        error = "Informe uma imagem para gerar o Compose."
    return templates.TemplateResponse(
        request,
        "partials/create_compose.html",
        {
            "image": image_ref,
            "stack_name": stack_name,
            "compose_content": compose_content,
            "env_content": None,
            "error": error,
            "success": None,
            "output": None,
        },
    )


@router.post("/docker/create", response_class=HTMLResponse)
def create_stack(
    request: Request,
    stack_name: str = Form(...),
    image: str = Form(""),
    compose_content: str = Form(...),
    env_content: str | None = Form(None),
    user: str = Depends(require_auth),
    compose_svc: ComposeService = Depends(get_compose_service),
    hub_cache: HubCache = Depends(get_hub_cache),
):
    ok, message = compose_svc.create_stack(stack_name, compose_content, env_content)
    if ok:
        for used in compose_svc.extract_images(compose_content):
            hub_cache.record_used_image(used, stack_name)
        return templates.TemplateResponse(
            request,
            "partials/create_result.html",
            {"message": message, "stack_name": stack_name},
        )
    return templates.TemplateResponse(
        request,
        "partials/create_compose.html",
        {
            "image": image,
            "stack_name": stack_name,
            "compose_content": compose_content,
            "env_content": env_content,
            "error": message,
            "success": None,
            "output": None,
        },
    )
