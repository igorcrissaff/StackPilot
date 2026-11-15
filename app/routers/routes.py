from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from app.auth import require_auth
from app.dependencies import get_effective_base_domain, get_traefik_service, templates
from app.services.traefik_service import RouteConfig, TraefikService

router = APIRouter(prefix="/routes", tags=["routes"])


@router.get("", response_class=HTMLResponse)
def list_routes(
    request: Request,
    user: str = Depends(require_auth),
    base_domain: str = Depends(get_effective_base_domain),
    traefik_svc: TraefikService = Depends(get_traefik_service),
):
    routes = traefik_svc.list_routes()
    return templates.TemplateResponse(
        request,
        "partials/route_list.html",
        {"routes": routes, "error": None, "base_domain": base_domain},
    )


@router.post("", response_class=HTMLResponse)
def upsert_route(
    request: Request,
    name: str = Form(...),
    subdomain: str = Form(...),
    target_url: str = Form(...),
    user: str = Depends(require_auth),
    base_domain: str = Depends(get_effective_base_domain),
    traefik_svc: TraefikService = Depends(get_traefik_service),
):
    error = None
    try:
        route = RouteConfig(
            name=name.strip(),
            subdomain=subdomain.strip(),
            target_url=target_url.strip(),
        )
        traefik_svc.upsert_route(route)
    except ValidationError as exc:
        error = "; ".join(e["msg"] for e in exc.errors())

    routes = traefik_svc.list_routes()
    return templates.TemplateResponse(
        request,
        "partials/route_list.html",
        {"routes": routes, "error": error, "base_domain": base_domain},
    )


@router.delete("/{name}", response_class=HTMLResponse)
def delete_route(
    request: Request,
    name: str,
    user: str = Depends(require_auth),
    base_domain: str = Depends(get_effective_base_domain),
    traefik_svc: TraefikService = Depends(get_traefik_service),
):
    traefik_svc.delete_route(name)
    routes = traefik_svc.list_routes()
    return templates.TemplateResponse(
        request,
        "partials/route_list.html",
        {"routes": routes, "error": None, "base_domain": base_domain},
    )


@router.get("/{name}/edit", response_class=HTMLResponse)
def edit_route_form(
    request: Request,
    name: str,
    user: str = Depends(require_auth),
    base_domain: str = Depends(get_effective_base_domain),
    traefik_svc: TraefikService = Depends(get_traefik_service),
):
    route = traefik_svc.get_route(name)
    if not route:
        raise HTTPException(status_code=404, detail=f"Route '{name}' not found")
    return templates.TemplateResponse(
        request,
        "partials/route_edit_row.html",
        {"r": route, "base_domain": base_domain},
    )
