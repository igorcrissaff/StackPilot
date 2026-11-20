from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import require_auth, verify_credentials
from app.config import get_settings
from app.dependencies import (
    get_docker_service,
    get_metrics_collector,
    get_metrics_history,
    get_metrics_service,
    get_metrics_settings,
    templates,
)
from app.routers import containers, docker, metrics, settings as settings_router
from app.services.docker_service import DockerUnavailableError
from app.services.metrics_collector import MetricsCollector
from app.services.metrics_settings import DEFAULT_REFRESH_SECONDS

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    collector = MetricsCollector(
        get_metrics_service(),
        get_metrics_history(),
        get_metrics_settings(),
    )
    app.state.metrics_collector = collector
    collector.start()
    try:
        yield
    finally:
        collector.stop()


app = FastAPI(title="StackPilot", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(containers.router)
app.include_router(docker.router)
app.include_router(metrics.router)
app.include_router(settings_router.router)


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
    metrics_svc=Depends(get_metrics_service),
    metrics_settings=Depends(get_metrics_settings),
    collector=Depends(get_metrics_collector),
):
    container_error = None
    images_error = None
    metrics = None
    metrics_error = None
    containers = []
    images_count = 0
    try:
        metrics = metrics_svc.collect()
    except Exception as exc:
        metrics_error = f"Não foi possível coletar métricas: {exc}"
    try:
        containers = docker_svc.list_containers()
    except DockerUnavailableError as exc:
        container_error = str(exc)
    try:
        images_count = len(docker_svc.list_images())
    except DockerUnavailableError as exc:
        images_error = str(exc)

    try:
        metrics_interval = metrics_settings.get_refresh_interval()
    except Exception:
        metrics_interval = DEFAULT_REFRESH_SECONDS
    chart = collector.chart_series(30, metrics_interval)

    running_containers = sum(1 for c in containers if getattr(c, "status", "") == "running")
    stopped_containers = len(containers) - running_containers
    stacks_set = {getattr(c, "stack", None) for c in containers if getattr(c, "stack", None)}
    stacks_count = len(stacks_set)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "host": settings.host_info,
            "containers": containers,
            "container_error": container_error,
            "images_count": images_count,
            "images_error": images_error,
            "running_containers": running_containers,
            "stopped_containers": stopped_containers,
            "stacks_count": stacks_count,
            "metrics": metrics,
            "metrics_error": metrics_error,
            "chart": chart,
            "interval": metrics_interval,
            "multiplier": 30,
            "multipliers": list(range(10, 101, 10)),
        },
    )
