from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.auth import require_auth
from app.dependencies import get_task_service, templates
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_class=HTMLResponse)
def tasks_page(
    request: Request,
    user: str = Depends(require_auth),
    task_svc: TaskService = Depends(get_task_service),
):
    tasks = task_svc.list_tasks()
    return templates.TemplateResponse(
        request,
        "tasks.html",
        {"user": user, "tasks": tasks},
    )


@router.get("/list", response_class=HTMLResponse)
def tasks_list_partial(
    request: Request,
    user: str = Depends(require_auth),
    task_svc: TaskService = Depends(get_task_service),
):
    tasks = task_svc.list_tasks()
    return templates.TemplateResponse(
        request,
        "partials/task_list.html",
        {"tasks": tasks},
    )
