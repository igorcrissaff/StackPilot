from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import require_auth, verify_credentials
from app.config import get_settings
from app.dependencies import get_docker_service, get_traefik_service, templates
from app.routers import containers, docker, routes as routes_router
from app.services.docker_service import DockerUnavailableError
from app.services.traefik_service import TraefikService

settings = get_settings()
app = FastAPI(title="StackPilot")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

app.include_router(containers.router)
app.include_router(docker.router)
app.include_router(routes_router.router)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    cfg = get_settings()
    if not verify_credentials(username, password, cfg.stackpilot_user, cfg.stackpilot_password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid username or password"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    request.session["user"] = username
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    user: str = Depends(require_auth),
    docker_svc=Depends(get_docker_service),
    traefik_svc: TraefikService = Depends(get_traefik_service),
):
    container_error = None
    route_error = None
    containers = []
    routes = []
    try:
        containers = docker_svc.list_containers()
    except DockerUnavailableError as exc:
        container_error = str(exc)
    try:
        routes = traefik_svc.list_routes()
    except Exception as exc:
        route_error = str(exc)

    running_containers = sum(1 for c in containers if getattr(c, "status", "") == "running")
    stopped_containers = len(containers) - running_containers
    stacks_set = {getattr(c, "stack", None) for c in containers if getattr(c, "stack", None)}
    stacks_count = len(stacks_set)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "containers": containers,
            "container_error": container_error,
            "routes": routes,
            "route_error": route_error,
            "running_containers": running_containers,
            "stopped_containers": stopped_containers,
            "base_domain": settings.base_domain,
            "stacks_count": stacks_count,
        },
    )
