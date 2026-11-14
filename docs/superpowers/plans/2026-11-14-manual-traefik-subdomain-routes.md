# Manual Traefik Subdomain Routes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every manually managed Traefik route an HTTP subdomain of a single configurable local base domain (`BASE_DOMAIN`, default `home.arpa`), resolved via the machine's `hosts` file.

**Architecture:** The form accepts only a DNS label; `TraefikService` composes `<subdomain>.<base_domain>` and writes `Host()` routers on the `web` entrypoint to the existing file-provider YAML. TLS, `websecure`, and `certResolver` are removed from the route model, UI, and Traefik compose. Delivery stays single-machine; the panel only shows the `hosts` line to add.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2 / pydantic-settings, Jinja2, PyYAML, Traefik v3 file provider, pytest.

**Spec:** `docs/superpowers/specs/2026-11-14-manual-traefik-subdomain-routes-design.md`

## Global Constraints

- `BASE_DOMAIN` default is exactly `home.arpa`; it is a bare domain (no scheme, slash, or whitespace); normalize to lowercase and strip trailing dot(s).
- Routes are HTTP only: `entryPoints: ["web"]`, port 80. No `tls`, no `certResolver`, no `websecure`, no `443:443`.
- Subdomain is a single DNS label: `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`, lowercase, no dots, max 63 chars.
- `name` remains the route identifier (used in `/routes/{name}`); `subdomain` is the host label. They may differ.
- Do not edit the `hosts` file automatically; show `127.0.0.1 <fqdn>` (with a note to use the host IP from another machine).
- No container-derived routes, no local DNS server, no TLS/ACME/CA, no multi-host support.
- Run tests with `.\.venv\Scripts\python.exe -m pytest -q` from the repo root.

## Review Focus

1. Subdomain input with dots, spaces, or uppercase: normalize case/space, reject dots, never emit `Host(\`foo.bar.home.arpa\`)`.
2. `BASE_DOMAIN` with scheme, slash, whitespace, or trailing dot: reject or normalize, never emit a malformed `Host()`.
3. The existing YAML also contains routers for domains outside `BASE_DOMAIN`: they must be left untouched and not listed/deleted.
4. `BASE_DOMAIN` changed while routes exist: old routes disappear from the UI but remain on disk (no data loss, no rewrite).
5. `name` and `subdomain` differ: creating and editing must use `name` as identity and `subdomain` only for the host.

---

### Task 1: Configurable base domain

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`
- Modify: `.env.wsl.example`
- Test: `tests/test_config.py`
- Test: `tests/test_deployment_assets.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Settings.base_domain: str` (default `"home.arpa"`, validated/normalized). `.env.example` and `.env.wsl.example` contain `BASE_DOMAIN=home.arpa`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py` (import `pytest` and `ValidationError`):

```python
import pytest
from pydantic import ValidationError


def test_settings_base_domain_default(monkeypatch):
    monkeypatch.delenv("BASE_DOMAIN", raising=False)
    settings = Settings(_env_file=None)
    assert settings.base_domain == "home.arpa"


def test_settings_normalizes_base_domain(monkeypatch):
    monkeypatch.setenv("BASE_DOMAIN", " Lab.Local. ")
    settings = Settings(_env_file=None)
    assert settings.base_domain == "lab.local"


def test_settings_rejects_invalid_base_domain():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, base_domain="http://lab.local")
```

Add to `tests/test_deployment_assets.py`:

```python
def test_env_examples_define_base_domain():
    for path in (Path(".env.example"), Path(".env.wsl.example")):
        assert _env_map(path)["BASE_DOMAIN"] == "home.arpa"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_deployment_assets.py::test_env_examples_define_base_domain -v`

Expected: FAIL — `Settings` has no `base_domain` / `KeyError: 'BASE_DOMAIN'`.

- [ ] **Step 3: Implement the setting**

In `app/config.py`, import `field_validator`, add `base_domain: str = "home.arpa"`, and add:

```python
@field_validator("base_domain")
@classmethod
def validate_base_domain(cls, v: str) -> str:
    v = v.strip().lower().rstrip(".")
    if not v or "://" in v or "/" in v or any(ch.isspace() for ch in v):
        raise ValueError("BASE_DOMAIN must be a bare domain, e.g. home.arpa")
    return v
```

Add `BASE_DOMAIN=home.arpa` to `.env.example` and `.env.wsl.example`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_deployment_assets.py::test_env_examples_define_base_domain -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/config.py .env.example .env.wsl.example tests/test_config.py tests/test_deployment_assets.py
git commit -m "feat: add configurable BASE_DOMAIN for local routes"
```

---

### Task 2: Subdomain-based route model and service

**Files:**
- Modify: `app/services/traefik_service.py`
- Test: `tests/test_traefik_service.py`

**Interfaces:**
- Consumes: base domain string (from `Settings.base_domain` at wiring time).
- Produces:
  - `RouteConfig(name: str, subdomain: str, target_url: str)` — no `tls`; `subdomain` normalized (`strip().lower()`) and validated as a DNS label.
  - `TraefikService(dynamic_dir: Path, base_domain: str)`.
  - `list_routes() -> list[RouteConfig]` (only routers under `.<base_domain>`), `get_route(name: str) -> RouteConfig | None`, `upsert_route(route: RouteConfig) -> None`, `delete_route(name: str) -> bool`.
  - YAML written: router `rule == "Host(\`<subdomain>.<base_domain>\`)"`, `entryPoints == ["web"]`, `service == name`, no `tls` key; service URL == `target_url`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_traefik_service.py` with tests covering:

```python
import pytest
import yaml
from pydantic import ValidationError

from app.services.traefik_service import RouteConfig, TraefikService


def test_upsert_writes_http_router_under_base_domain(tmp_path):
    svc = TraefikService(dynamic_dir=tmp_path, base_domain="home.arpa")
    svc.upsert_route(
        RouteConfig(name="portainer-ui", subdomain="portainer", target_url="http://portainer:9000")
    )

    data = yaml.safe_load((tmp_path / "stackpilot-routes.yml").read_text(encoding="utf-8"))
    router = data["http"]["routers"]["portainer-ui"]
    assert router["rule"] == "Host(`portainer.home.arpa`)"
    assert router["entryPoints"] == ["web"]
    assert router["service"] == "portainer-ui"
    assert "tls" not in router
    assert data["http"]["services"]["portainer-ui"]["loadBalancer"]["servers"][0]["url"] == "http://portainer:9000"


def test_list_routes_returns_subdomain(tmp_path):
    svc = TraefikService(dynamic_dir=tmp_path, base_domain="home.arpa")
    svc.upsert_route(RouteConfig(name="grafana", subdomain="grafana", target_url="http://grafana:3000"))

    routes = svc.list_routes()
    assert len(routes) == 1
    assert routes[0].name == "grafana"
    assert routes[0].subdomain == "grafana"
    assert routes[0].target_url == "http://grafana:3000"


def test_subdomain_is_normalized_and_dots_rejected():
    assert RouteConfig(name="x", subdomain=" Grafana ", target_url="http://g:3000").subdomain == "grafana"
    with pytest.raises(ValidationError):
        RouteConfig(name="x", subdomain="grafana.home.arpa", target_url="http://g:3000")


def test_list_routes_ignores_routers_outside_base_domain(tmp_path):
    (tmp_path / "stackpilot-routes.yml").write_text(
        yaml.safe_dump(
            {
                "http": {
                    "routers": {
                        "keep": {"rule": "Host(`keep.home.arpa`)", "service": "keep"},
                        "other": {"rule": "Host(`other.example`)", "service": "other"},
                    },
                    "services": {
                        "keep": {"loadBalancer": {"servers": [{"url": "http://keep:80"}]}},
                        "other": {"loadBalancer": {"servers": [{"url": "http://other:80"}]}},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    svc = TraefikService(dynamic_dir=tmp_path, base_domain="home.arpa")
    assert [r.name for r in svc.list_routes()] == ["keep"]

    svc.upsert_route(RouteConfig(name="new", subdomain="new", target_url="http://new:80"))
    data = yaml.safe_load((tmp_path / "stackpilot-routes.yml").read_text(encoding="utf-8"))
    assert data["http"]["routers"]["other"]["rule"] == "Host(`other.example`)"


def test_get_and_delete_route(tmp_path):
    svc = TraefikService(dynamic_dir=tmp_path, base_domain="home.arpa")
    svc.upsert_route(RouteConfig(name="app1", subdomain="app1", target_url="http://app1:8080"))

    found = svc.get_route("app1")
    assert found is not None and found.subdomain == "app1"
    assert svc.delete_route("app1") is True
    assert svc.list_routes() == []
    assert svc.delete_route("missing") is False


def test_invalid_target_url_rejected():
    with pytest.raises(ValidationError):
        RouteConfig(name="bad", subdomain="bad", target_url="not-a-url")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_traefik_service.py -v`

Expected: FAIL — `RouteConfig` requires `domain`/`tls`; `TraefikService` rejects `base_domain`.

- [ ] **Step 3: Implement the model and service**

In `app/services/traefik_service.py`:
- Replace `DOMAIN_RE` with `SUBDOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")`.
- `RouteConfig`: fields `name`, `subdomain`, `target_url`; `validate_subdomain` does `v = v.strip().lower()` then rejects non-matches with `ValueError("Invalid subdomain")`; keep `validate_name` and `validate_target_url`.
- `TraefikService.__init__(self, dynamic_dir: Path, base_domain: str)`: store `self.base_domain = base_domain.strip().lower().rstrip(".")`.
- `upsert_route`: `router_def = {"rule": f"Host(\`{route.subdomain}.{self.base_domain}\`)", "service": route.name, "entryPoints": ["web"]}`; no `tls` key.
- `list_routes`: derive `domain` from the rule; skip entries not ending in `f".{self.base_domain}"` or whose prefix fails `SUBDOMAIN_RE`; return `RouteConfig(name=..., subdomain=..., target_url=...)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_traefik_service.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/traefik_service.py tests/test_traefik_service.py
git commit -m "feat: compose Traefik Host rules from subdomains"
```

---

### Task 3: Wire subdomains through router and UI

**Files:**
- Modify: `app/routers/routes.py`
- Modify: `app/main.py`
- Modify: `app/templates/dashboard.html`
- Modify: `app/templates/partials/route_list.html`
- Modify: `app/templates/partials/route_edit_row.html`
- Test: `tests/test_routers.py`

**Interfaces:**
- Consumes: `RouteConfig(subdomain=...)`, `TraefikService.list_routes/get_route/upsert_route/delete_route`, `get_settings().base_domain`.
- Produces: form field `subdomain`; every route template gets `base_domain: str`; dashboard context no longer contains `tls_routes`.

- [ ] **Step 1: Write the failing tests**

Update `tests/test_routers.py` route tests to use subdomains:

```python
def test_dashboard_renders_routes_with_base_domain():
    mock_docker = MagicMock()
    mock_docker.list_containers.return_value = [
        ContainerInfo(id="1234567890ab", short_id="1234567890ab", name="jellyfin", image="jellyfin/jellyfin:latest", status="running")
    ]
    mock_traefik = MagicMock()
    mock_traefik.list_routes.return_value = [
        RouteConfig(name="jellyfin", subdomain="jellyfin", target_url="http://jellyfin:8096")
    ]

    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    app.dependency_overrides[get_traefik_service] = lambda: mock_traefik
    try:
        resp = _authed_client().get("/")
        assert resp.status_code == 200
        assert "jellyfin" in resp.text
        assert "jellyfin.home.arpa" in resp.text
        assert "Compose Stacks" in resp.text
        assert "Traefik Routes" in resp.text
        assert "Docker Socket" in resp.text
        assert 'name="subdomain"' in resp.text
        assert 'name="tls"' not in resp.text
    finally:
        app.dependency_overrides.clear()


def test_create_and_delete_route():
    mock_traefik = MagicMock()
    mock_traefik.list_routes.return_value = []
    mock_traefik.delete_route.return_value = True
    app.dependency_overrides[get_traefik_service] = lambda: mock_traefik
    try:
        client = _authed_client()
        resp = client.post(
            "/routes",
            data={"name": "plex-ui", "subdomain": "plex", "target_url": "http://plex:32400"},
        )
        assert resp.status_code == 200
        mock_traefik.upsert_route.assert_called_once()
        route = mock_traefik.upsert_route.call_args.args[0]
        assert route.name == "plex-ui"
        assert route.subdomain == "plex"

        resp_del = client.delete("/routes/plex-ui")
        assert resp_del.status_code == 200
        mock_traefik.delete_route.assert_called_once_with("plex-ui")
    finally:
        app.dependency_overrides.clear()


def test_create_route_rejects_dotted_subdomain():
    mock_traefik = MagicMock()
    mock_traefik.list_routes.return_value = []
    app.dependency_overrides[get_traefik_service] = lambda: mock_traefik
    try:
        resp = _authed_client().post(
            "/routes",
            data={"name": "plex", "subdomain": "plex.home.arpa", "target_url": "http://plex:32400"},
        )
        assert resp.status_code == 200
        assert "Invalid subdomain" in resp.text
        mock_traefik.upsert_route.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_edit_route_form_uses_subdomain():
    mock_traefik = MagicMock()
    mock_traefik.get_route.return_value = RouteConfig(
        name="plex", subdomain="plex", target_url="http://plex:32400"
    )
    app.dependency_overrides[get_traefik_service] = lambda: mock_traefik
    try:
        resp = _authed_client().get("/routes/plex/edit")
        assert resp.status_code == 200
        assert 'name="subdomain"' in resp.text
        assert "plex" in resp.text
        assert "http://plex:32400" in resp.text

        mock_traefik.get_route.return_value = None
        assert _authed_client().get("/routes/missing/edit").status_code == 404
    finally:
        app.dependency_overrides.clear()
```

Remove the old `RouteConfig(..., domain=..., tls=...)` usages in `test_routers.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_routers.py -v`

Expected: FAIL — forms still use `domain`; templates reference `tls_routes`/`r.domain`.

- [ ] **Step 3: Implement the router and templates**

- `app/routers/routes.py`: import `get_settings` from `app.config`; read `subdomain: str = Form(...)` instead of `domain`; construct `RouteConfig(name=name.strip(), subdomain=subdomain.strip(), target_url=target_url.strip())`; add `"base_domain": get_settings().base_domain` to every template context; remove the `tls` form parameter.
- `app/main.py`: remove `tls_routes` computation and context key; add `"base_domain": settings.base_domain`.
- `app/templates/dashboard.html`: rename the input to `subdomain` with placeholder `ex: jellyfin` and label `Subdomínio`; remove the TLS checkbox; replace the HTTPS/HTTP counter with a single HTTP label; add a hint near the form: `Resolução local: adicione 127.0.0.1 <sub>.{{ base_domain }} ao arquivo hosts (use o IP do host se navegar de outra máquina).`
- `app/templates/partials/route_list.html`: show `{{ r.subdomain }}.{{ base_domain }}`, always link `http://`, remove the TLS column and badges.
- `app/templates/partials/route_edit_row.html`: input `name="subdomain"` with `value="{{ r.subdomain }}"` and a `.{{ base_domain }}` suffix; remove the TLS checkbox cell.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_routers.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/routers/routes.py app/main.py app/templates/dashboard.html app/templates/partials/route_list.html app/templates/partials/route_edit_row.html tests/test_routers.py
git commit -m "feat: manage Traefik routes as HTTP subdomains"
```

---

### Task 4: HTTP-only Traefik deploy and documentation

**Files:**
- Modify: `deploy/docker-compose.traefik.yml`
- Modify: `docs/deploy-wsl.md`
- Modify: `README.md`
- Test: `tests/test_deployment_assets.py`

**Interfaces:**
- Consumes: `BASE_DOMAIN` documented in the env examples (Task 1).
- Produces: Traefik publishes only `80:80` and `127.0.0.1:8080:8080`; no `websecure`/`443`; docs explain subdomains, hosts, and HTTP-only.

- [ ] **Step 1: Write the failing tests**

Update `tests/test_deployment_assets.py`:

```python
def test_traefik_compose_binds_dynamic_dir_and_ports():
    traefik = _traefik()["services"]["traefik"]
    volumes = traefik["volumes"]
    assert any(v.endswith(":/etc/traefik/dynamic") for v in volumes)
    assert any("${TRAEFIK_DYNAMIC_DIR:" in v for v in volumes)
    assert "80:80" in traefik["ports"]
    assert "127.0.0.1:8080:8080" in traefik["ports"]
    assert "443:443" not in traefik["ports"]
    assert not any("websecure" in arg for arg in traefik["command"])


def test_wsl_deploy_doc_documents_subdomain_routes():
    text = DOC.read_text(encoding="utf-8")
    for needle in ("BASE_DOMAIN", "home.arpa", "hosts", "127.0.0.1"):
        assert needle in text


def test_readme_documents_base_domain():
    assert "BASE_DOMAIN" in Path("README.md").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deployment_assets.py -v`

Expected: FAIL — compose still publishes `443:443` and configures `websecure`; docs/README lack the new wording.

- [ ] **Step 3: Implement the compose and docs changes**

- `deploy/docker-compose.traefik.yml`: delete the `--entrypoints.websecure.address=:443` command line and the `"443:443"` port; keep `web`, file provider `watch`, and the dashboard bind.
- `docs/deploy-wsl.md`: rewrite the Traefik routes section to state that routes are `subdomain.<BASE_DOMAIN>` served over HTTP on port 80, created via the panel, with a `hosts` example (`127.0.0.1 grafana.home.arpa`) and the note to use the host IP from another machine; state TLS is not enabled in this cycle and remove the old `websecure`/TLS wording.
- `README.md`: update the routing bullet to say HTTP subdomains of `BASE_DOMAIN` with `hosts` resolution; update the metrics bullet to drop “rotas TLS”.

- [ ] **Step 4: Run the full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add deploy/docker-compose.traefik.yml docs/deploy-wsl.md README.md tests/test_deployment_assets.py
git commit -m "chore: serve Traefik routes over HTTP subdomains"
```
