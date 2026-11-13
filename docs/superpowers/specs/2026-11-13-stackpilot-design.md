# StackPilot — Design Document

## 1. Intent & Why
A lightweight, self-hosted control panel for home servers (homelabs) to manage Docker containers and reverse proxy routing (Traefik) without needing complex multi-node orchestration or heavy frontend toolchains. Built in Python for ease of maintenance.

## 2. Goals, Non-Goals & Anti-Goals
- **Goals:**
  - Manage local Docker containers (list, start, stop, restart, remove, inspect logs/status) via `/var/run/docker.sock`.
  - Manage Traefik HTTP/HTTPS routing rules (domain -> container/port, TLS toggle) via Traefik dynamic configuration files (YAML) or container labels.
  - Single-stack Python codebase (FastAPI + Jinja2 + HTMX) with minimal resource footprint.
  - Simple authentication (single-admin login via environment variables or local SQLite).
- **Non-Goals:**
  - Multi-server / remote node management (SSH/agents).
  - Multi-user RBAC or complex team permissions.
  - Full Docker Compose editor/orchestrator (beyond basic stack visibility).
- **Anti-Goals:**
  - Requiring Node.js/npm build steps for the frontend.
  - Breaking existing Traefik routing on invalid user input (must validate before writing config).

## 3. Constraints
- **Language:** Python 3.11+
- **Backend:** FastAPI + Uvicorn
- **Frontend:** Jinja2 templates + HTMX + Tailwind CSS (via CDN or standalone CLI, no Node.js runtime required)
- **Docker Integration:** `docker` (`docker-py`) Python SDK
- **Proxy Integration:** Traefik v2/v3 via file provider (dynamic YAML directory mounted to both StackPilot and Traefik)

## 4. Approaches Considered
1. **FastAPI + Jinja2/HTMX + Traefik (Chosen):** 100% Python, zero frontend build step, low memory usage, native Traefik hot-reload and automatic Let's Encrypt TLS.
2. **FastAPI + React/Vue + Nginx:** Higher maintenance overhead (two ecosystems) and fragile programmatic Nginx config reloads.

## 5. Architecture & Key Decisions
- **Docker Service (`app/services/docker_service.py`):** Wraps `docker.from_env()` to list containers, stream/fetch logs, and run lifecycle actions.
- **Traefik Service (`app/services/traefik_service.py`):** Reads/writes validated YAML route files into a configured `TRAEFIK_DYNAMIC_DIR` (e.g., `/etc/traefik/dynamic/stackpilot-routes.yml`). Uses Pydantic models to validate domains, target services, and entrypoints before writing.
- **Web UI (`app/routers/` + `app/templates/`):** Server-rendered HTML with HTMX partials for live container status polling, log viewing, and route creation/deletion without full page reloads.
- **Deployment:** Packaged as a `Dockerfile` + `docker-compose.yml` alongside Traefik, mounting `/var/run/docker.sock` and the shared Traefik dynamic config volume.

## 6. Open / Left to Builder
- Exact UI styling details (Tailwind classes/layout).
- Specific auth mechanism (HTTP Basic / session cookie with env-configured password hash).
