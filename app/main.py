from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import require_auth, verify_credentials
from app.config import get_settings
from app.dependencies import get_docker_service, templates
from app.routers import containers, docker
from app.services.docker_service import DockerUnavailableError

settings = get_settings()
app = FastAPI(title="StackPilot")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(containers.router)
app.include_router(docker.router)


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
):
    container_error = None
    images_error = None
    containers = []
    images_count = 0
    try:
        containers = docker_svc.list_containers()
    except DockerUnavailableError as exc:
        container_error = str(exc)
    try:
        images_count = len(docker_svc.list_images())
    except DockerUnavailableError as exc:
        images_error = str(exc)

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
            "images_count": images_count,
            "images_error": images_error,
            "running_containers": running_containers,
            "stopped_containers": stopped_containers,
            "stacks_count": stacks_count,
        },
    )
