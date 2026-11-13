# StackPilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight, self-hosted server control panel in Python for home servers to manage Docker containers and Traefik HTTP/HTTPS routing.

**Architecture:** FastAPI backend serving Jinja2 + HTMX HTML partials, wrapping `docker-py` for local Docker socket operations and Pydantic-validated YAML generation for Traefik's file provider.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Jinja2, HTMX, Tailwind CSS (CDN), `docker` (`docker-py`), PyYAML, Pydantic, pytest.

**Spec:** `docs/superpowers/specs/2026-11-13-stackpilot-design.md`

## Global Constraints
- Python 3.11+ only.
- No Node.js/npm build step for the frontend.
- Single-admin authentication via environment variables (`STACKPILOT_USER`, `STACKPILOT_PASSWORD`).
- Traefik routing managed via dynamic YAML files in `TRAEFIK_DYNAMIC_DIR` validated before writing.

## Review Focus
- Invalid domain names or target URLs in Traefik route creation must be rejected by Pydantic before writing YAML.
- Docker daemon unavailable (`/var/run/docker.sock` missing or permission denied) must return a graceful error state, not crash the app.
- Unauthenticated requests to any dashboard or API route must redirect to `/login` (or return 401).
- Deleting a non-existent Traefik route must be handled idempotently or return a clean 404.
- Container action on a non-existent container ID must return a clean 404/error partial.

---

### Task 1: Project Scaffolding & Configuration

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings` (Pydantic `BaseSettings` with `stackpilot_user: str`, `stackpilot_password: str`, `traefik_dynamic_dir: Path`, `secret_key: str`), `get_settings() -> Settings`

- [ ] **Step 1: Write the failing test**
```python
from app.config import get_settings

def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("STACKPILOT_PASSWORD", "secret123")
    settings = get_settings()
    assert settings.stackpilot_user == "admin"
    assert settings.stackpilot_password == "secret123"
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Create `pyproject.toml`, `app/__init__.py`, and `app/config.py`**
Define `pyproject.toml` with dependencies (`fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`, `docker`, `pyyaml`, `pydantic-settings`, `pytest`, `httpx`). Implement `Settings` and `get_settings()` in `app/config.py`.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add pyproject.toml app/__init__.py app/config.py tests/test_config.py
git commit -m "chore: scaffold project and configuration"
```

---

### Task 2: Docker Service

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/docker_service.py`
- Test: `tests/test_docker_service.py`

**Interfaces:**
- Produces: `ContainerInfo` (Pydantic model: `id`, `name`, `image`, `status`, `state`), `DockerService` with `list_containers() -> list[ContainerInfo]`, `container_action(container_id: str, action: str) -> None`, `get_logs(container_id: str, tail: int = 100) -> str`

- [ ] **Step 1: Write the failing tests**
Test `list_containers`, `container_action` (start/stop/restart/remove), `get_logs`, and graceful handling when Docker daemon is unavailable (`DockerException`) or container is not found (`NotFound`) using mocked `docker.DockerClient`.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_docker_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `DockerService` in `app/services/docker_service.py`**
Wrap `docker.from_env()` with clean exception mapping (`DockerUnavailableError`, `ContainerNotFoundError`).

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_docker_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add app/services/ tests/test_docker_service.py
git commit -m "feat: add DockerService for container management"
```

---

### Task 3: Traefik Service

**Files:**
- Create: `app/services/traefik_service.py`
- Test: `tests/test_traefik_service.py`

**Interfaces:**
- Produces: `RouteConfig` (Pydantic model: `name: str`, `domain: str`, `target_url: str`, `tls: bool = True`), `TraefikService(dynamic_dir: Path)` with `list_routes() -> list[RouteConfig]`, `upsert_route(route: RouteConfig) -> None`, `delete_route(name: str) -> bool`

- [ ] **Step 1: Write the failing tests**
Test `upsert_route` writes valid Traefik v2/v3 YAML (`http.routers`, `http.services`), `list_routes` parses it back, `delete_route` removes it, and invalid domain/URL raises `ValidationError` without writing to disk.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_traefik_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `TraefikService` in `app/services/traefik_service.py`**
Use Pydantic regex/URL validation and `yaml.safe_dump` / `yaml.safe_load` to manage `stackpilot-routes.yml` inside `dynamic_dir`.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_traefik_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add app/services/traefik_service.py tests/test_traefik_service.py
git commit -m "feat: add TraefikService for dynamic YAML route management"
```

---

### Task 4: Authentication & FastAPI App Shell

**Files:**
- Create: `app/auth.py`
- Create: `app/main.py`
- Create: `app/templates/base.html`
- Create: `app/templates/login.html`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `get_settings() -> Settings`
- Produces: `app: FastAPI`, `require_auth(request: Request) -> str`

- [ ] **Step 1: Write the failing tests**
Test that `GET /` redirects to `/login` when unauthenticated, `POST /login` with valid credentials sets session cookie and redirects to `/`, and invalid credentials return 401.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_auth.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `app/auth.py`, `app/main.py`, and base/login templates**
Use `itsdangerous` signed session cookies via Starlette's `SessionMiddleware`.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add app/auth.py app/main.py app/templates/ tests/test_auth.py
git commit -m "feat: add session authentication and FastAPI app shell"
```

---

### Task 5: Containers & Traefik Web UI (Jinja2 + HTMX)

**Files:**
- Create: `app/routers/__init__.py`
- Create: `app/routers/containers.py`
- Create: `app/routers/routes.py`
- Create: `app/templates/dashboard.html`
- Create: `app/templates/partials/container_list.html`
- Create: `app/templates/partials/container_logs.html`
- Create: `app/templates/partials/route_list.html`
- Modify: `app/main.py`
- Test: `tests/test_routers.py`

**Interfaces:**
- Consumes: `DockerService`, `TraefikService`, `require_auth`

- [ ] **Step 1: Write the failing tests**
Test authenticated `GET /`, `POST /containers/{id}/{action}`, `GET /containers/{id}/logs`, `POST /routes`, and `DELETE /routes/{name}` using `TestClient` with mocked services.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_routers.py -v`
Expected: FAIL

- [ ] **Step 3: Implement routers and HTMX templates**
Wire `containers` and `routes` routers into `app/main.py` and create clean Tailwind + HTMX partials.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_routers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add app/routers/ app/templates/ app/main.py tests/test_routers.py
git commit -m "feat: add containers and Traefik routes HTMX UI"
```

---

### Task 6: Docker Packaging & Deployment

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: Create `Dockerfile` (Python 3.11-slim, non-root or socket-compatible, uvicorn entrypoint)**
- [ ] **Step 2: Create `docker-compose.yml` (StackPilot + Traefik v3 sharing `traefik_dynamic` volume and `/var/run/docker.sock`)**
- [ ] **Step 3: Create `.env.example` with `STACKPILOT_USER`, `STACKPILOT_PASSWORD`, `SECRET_KEY`**
- [ ] **Step 4: Verify full test suite**
Run: `pytest -v`
Expected: All tests PASS.
- [ ] **Step 5: Commit**
```bash
git add Dockerfile docker-compose.yml .env.example
git commit -m "chore: add Docker and Compose deployment files"
```
