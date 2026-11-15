# Docker Hub Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Docker Desktop-style view where the admin searches Docker Hub images (cached in SQLite), picks a tag, edits a generated compose file, and deploys it as a new stack.

**Architecture:** A `DockerHubService` talks to the public Hub API through `httpx` and caches search/tag payloads in SQLite (`HubCache`). A new `/docker` page with Images/Containers tabs reuses the existing `DockerService`/`ComposeService` and compose editor patterns; `ComposeService.create_stack` writes `STACKS_DIR/<stack>/compose.yaml` and runs `docker compose up -d`.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, HTMX, Tailwind (CDN), `httpx`, stdlib `sqlite3`, docker-py, `docker compose` via subprocess, pytest.

**Spec:** `docs/superpowers/specs/2026-11-15-docker-hub-integration-design.md`

## File Structure

- `app/config.py` — new Hub/compose/network settings (modify).
- `app/dependencies.py` — `get_hub_cache`, `get_dockerhub_service`, compose kwargs (modify).
- `app/services/hub_cache.py` — SQLite cache and `UsedImage` model (create).
- `app/services/dockerhub_service.py` — Hub API client, models, errors (create).
- `app/services/docker_service.py` — `ImageInfo` + `list_images` (modify).
- `app/services/compose_service.py` — starter compose, `create_stack`, `_run_compose_up` (modify).
- `app/routers/docker.py` — `/docker`, `/docker/images`, `/hub/*`, `/docker/create` (create).
- `app/main.py` — include the Docker router (modify).
- `app/templates/docker.html` — Docker Desktop-style shell with Images/Containers tabs (create).
- `app/templates/partials/image_list.html`, `hub_search.html`, `hub_tags.html`, `create_compose.html`, `create_result.html` (create).
- `app/templates/dashboard.html` — sidebar link to `/docker` (modify).
- `tests/test_hub_cache.py`, `tests/test_dockerhub_service.py`, `tests/test_docker_router.py` (create).
- `tests/test_config.py`, `tests/test_deployment_assets.py`, `tests/test_docker_service.py`, `tests/test_compose_service.py`, `tests/test_routers.py` (modify).
- `pyproject.toml`, `.env.example`, `.env.wsl.example`, `docker-compose.yml`, `.gitignore`, `README.md` (modify).

## Global Constraints

- Python 3.11+, FastAPI + Jinja2 + HTMX + Tailwind (CDN); no Node runtime.
- HTTP via `httpx`; SQLite via stdlib `sqlite3`; no ORM.
- Every new route uses `Depends(require_auth)`.
- `subprocess.run([...])` with argument lists only.
- Defaults (copied verbatim from spec): `HUB_DB_PATH=/opt/stackpilot/stackpilot.db` (fallback `./data/stackpilot.db`), `HUB_CACHE_TTL_SECONDS=86400`, `HUB_API_BASE=https://hub.docker.com`, `HUB_REQUEST_TIMEOUT_SECONDS=10.0`, `COMPOSE_UP_TIMEOUT_SECONDS=600`, `STACKPILOT_NETWORK=stackpilot_net`.
- `create_stack` refuses an existing `STACKS_DIR/<stack>`; starter compose has no `container_name` and attaches the external network.
- New stack dirs are confined to `STACKS_DIR` (path traversal blocked).
- `pytest` is not on PATH on this Windows workspace: every `Run: pytest ...` step below means `.venv\Scripts\python.exe -m pytest ...`.
- The `Commit` steps require the user's explicit request. If the user has not asked for commits in this session, run the verification step and leave the changes uncommitted for review.

## Review Focus

- **Hub `429` with no cache**: the user must get a readable error message, never a 500. Pinned in Task 3 (`test_search_429_without_cache_raises`) and Task 7 (`test_hub_search_error_shows_message`).
- **Registry/digest image refs** (`ghcr.io/org/app:1.2`, `nginx@sha256:...`) in service-name derivation and tag lookups. Pinned in Task 3 (`test_list_tags_rejects_registry_host`) and Task 5 (`test_derive_service_name`).
- **Path traversal in stack name** (`../x`). Pinned in Task 5 (`test_create_stack_rejects_traversal`).
- **Dangling local image** (`<none>`) crash/omission. Pinned in Task 4 (`test_list_images`) and Task 6 (`test_docker_page_renders_dangling_image`).
- **Failed deploy loses the edited compose**. Pinned in Task 8 (`test_create_failure_preserves_compose`).

---

### Task 1: Settings, httpx runtime dependency, env docs

**Files:**
- Modify: `app/config.py`
- Modify: `pyproject.toml`
- Modify: `.env.example`, `.env.wsl.example`
- Test: `tests/test_config.py`, `tests/test_deployment_assets.py`

**Interfaces:**
- Produces: `Settings` fields `hub_db_path: Path`, `hub_cache_ttl_seconds: int`, `hub_api_base: str`, `hub_request_timeout_seconds: float`, `compose_up_timeout_seconds: int`, `stackpilot_network: str`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_config.py`:

```python
def test_settings_hub_defaults():
    s = Settings(_env_file=None)
    assert s.hub_cache_ttl_seconds == 86400
    assert s.hub_api_base == "https://hub.docker.com"
    assert s.hub_request_timeout_seconds == 10.0
    assert s.compose_up_timeout_seconds == 600
    assert s.stackpilot_network == "stackpilot_net"


def test_settings_hub_env_overrides(monkeypatch):
    monkeypatch.setenv("HUB_CACHE_TTL_SECONDS", "60")
    monkeypatch.setenv("STACKPILOT_NETWORK", "mynet")
    s = Settings(_env_file=None)
    assert s.hub_cache_ttl_seconds == 60
    assert s.stackpilot_network == "mynet"
```

In `tests/test_deployment_assets.py`:

```python
def test_env_examples_define_docker_hub_defaults():
    for path in (Path(".env.example"), Path(".env.wsl.example")):
        env = _env_map(path)
        assert env["HUB_CACHE_TTL_SECONDS"] == "86400"
        assert env["COMPOSE_UP_TIMEOUT_SECONDS"] == "600"
        assert env["STACKPILOT_NETWORK"] == "stackpilot_net"
        assert "HUB_DB_PATH" in env
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py tests/test_deployment_assets.py -v`
Expected: FAIL (`AttributeError` on new settings; `KeyError` on env keys).

- [ ] **Step 3: Implement the settings and dependency**

Add to `Settings` in `app/config.py` (keep existing fields):

```python
hub_db_path: Path = Path("/opt/stackpilot/stackpilot.db")
hub_cache_ttl_seconds: int = 86400
hub_api_base: str = "https://hub.docker.com"
hub_request_timeout_seconds: float = 10.0
compose_up_timeout_seconds: int = 600
stackpilot_network: str = "stackpilot_net"
```

Add `"httpx>=0.27.0"` to `dependencies` in `pyproject.toml` (it may stay in `dev` too).

Append to `.env.example`:

```
HUB_DB_PATH=/opt/stackpilot/stackpilot.db
HUB_CACHE_TTL_SECONDS=86400
COMPOSE_UP_TIMEOUT_SECONDS=600
STACKPILOT_NETWORK=stackpilot_net
```

Append to `.env.wsl.example`:

```
HUB_DB_PATH=/opt/stackpilot/data/stackpilot.db
HUB_CACHE_TTL_SECONDS=86400
COMPOSE_UP_TIMEOUT_SECONDS=600
STACKPILOT_NETWORK=stackpilot_net
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py tests/test_deployment_assets.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/config.py pyproject.toml .env.example .env.wsl.example tests/test_config.py tests/test_deployment_assets.py
git commit -m "feat: add Docker Hub settings and httpx dependency"
```

---

### Task 2: SQLite cache (`HubCache`)

**Files:**
- Create: `app/services/hub_cache.py`
- Test: `tests/test_hub_cache.py`

**Interfaces:**
- Produces: `HubCache(db_path)`; `get_search(query, ttl_seconds) -> tuple[str | None, int | None, bool]` (payload JSON, `fetched_at`, `is_stale`); `set_search(query, payload)`; `get_tags(repo, ttl_seconds) -> tuple[str | None, int | None, bool]`; `set_tags(repo, payload)`; `record_used_image(image, stack_name)`; `list_used_images(limit=50) -> list[UsedImage]`; model `UsedImage(image, last_used_at, use_count, stack_name)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_hub_cache.py`:

```python
from unittest.mock import patch

from app.services.hub_cache import HubCache


def test_init_is_idempotent(tmp_path):
    db = tmp_path / "hub.db"
    HubCache(db)
    HubCache(db)  # must not raise


def test_search_cache_hit_and_stale(tmp_path):
    c = HubCache(tmp_path / "hub.db")
    assert c.get_search("jellyfin", 3600) == (None, None, False)
    c.set_search("jellyfin", '["x"]')
    payload, fetched_at, stale = c.get_search("jellyfin", 3600)
    assert (payload, stale) == ('["x"]', False)
    assert isinstance(fetched_at, int)
    assert c.get_search("jellyfin", -1)[2] is True


def test_tags_cache(tmp_path):
    c = HubCache(tmp_path / "hub.db")
    assert c.get_tags("library/nginx", 3600) == (None, None, False)
    c.set_tags("library/nginx", '["latest"]')
    assert c.get_tags("library/nginx", 3600)[0] == '["latest"]'


def test_record_used_image_increments(tmp_path):
    c = HubCache(tmp_path / "hub.db")
    c.record_used_image("jellyfin/jellyfin:latest", "jellyfin")
    c.record_used_image("jellyfin/jellyfin:latest", "jellyfin2")
    imgs = c.list_used_images()
    assert len(imgs) == 1
    assert imgs[0].image == "jellyfin/jellyfin:latest"
    assert imgs[0].use_count == 2
    assert imgs[0].stack_name == "jellyfin2"


def test_list_used_images_most_recent_first(tmp_path):
    c = HubCache(tmp_path / "hub.db")
    with patch("app.services.hub_cache.time.time", side_effect=[100, 200]):
        c.record_used_image("nginx:alpine", "a")
        c.record_used_image("redis:7", "b")
    assert [i.image for i in c.list_used_images()][0] == "redis:7"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_hub_cache.py -v`
Expected: FAIL (`ModuleNotFoundError: app.services.hub_cache`).

- [ ] **Step 3: Implement `HubCache`**

In `app/services/hub_cache.py`, create `HubCache` using `sqlite3`. Requirements:
- `__init__` stores `Path(db_path)` and calls `init_db()`.
- `_connect()` opens the DB, sets `PRAGMA journal_mode=WAL`, `row_factory = sqlite3.Row`.
- `init_db()` runs `CREATE TABLE IF NOT EXISTS` for the three tables named in the spec.
- `get_search`/`get_tags`: return `(None, None, False)` when absent; return `(payload, fetched_at, False)` when `int(time.time()) - fetched_at <= ttl_seconds`; else `(payload, fetched_at, True)`.
- `set_search`/`set_tags`: `INSERT ... ON CONFLICT(pk) DO UPDATE SET payload=excluded.payload, fetched_at=excluded.fetched_at`, with `fetched_at = int(time.time())`.
- Import `time` as a module (`import time`), not `from time import time`, so the tests can patch `app.services.hub_cache.time.time`.
- `record_used_image`: `INSERT ... ON CONFLICT(image) DO UPDATE SET last_used_at=excluded.last_used_at, use_count=used_images.use_count+1, stack_name=excluded.stack_name`.
- `list_used_images(limit=50)`: `ORDER BY last_used_at DESC LIMIT ?`, returning `UsedImage` models.
- Define `class UsedImage(BaseModel): image: str; last_used_at: int; use_count: int; stack_name: str | None = None`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_hub_cache.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/hub_cache.py tests/test_hub_cache.py
git commit -m "feat: add SQLite cache for Docker Hub searches and used images"
```

---

### Task 3: Docker Hub service

**Files:**
- Create: `app/services/dockerhub_service.py`
- Test: `tests/test_dockerhub_service.py`

**Interfaces:**
- Consumes: `HubCache.get_search/set_search/get_tags/set_tags`.
- Produces: `HubImage(repo_name: str, short_description: str = "", star_count: int = 0, pull_count: int = 0, is_official: bool = False)`, `HubTag(name: str, last_updated: str = "")`, `HubSearchResult(images: list[HubImage], stale: bool = False, fetched_at: int | None = None)`, `HubTagsResult(repo: str, tags: list[HubTag], stale: bool = False, fetched_at: int | None = None)`, `HubUnavailableError`, `InvalidImageReferenceError`, `split_reference(ref) -> tuple[str, str]`, and `DockerHubService(cache, ttl_seconds, api_base, timeout, client=None)` with `search_images(query) -> HubSearchResult` and `list_tags(repo) -> HubTagsResult`.

- [ ] **Step 1: Write the failing tests**

`tests/test_dockerhub_service.py`:

```python
import json

import httpx
import pytest

from app.services.dockerhub_service import (
    DockerHubService,
    HubUnavailableError,
    InvalidImageReferenceError,
    split_reference,
)
from app.services.hub_cache import HubCache


def _service(handler, cache, ttl=3600):
    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://hub.docker.com"
    )
    return DockerHubService(
        cache=cache, ttl_seconds=ttl, api_base="https://hub.docker.com", timeout=5, client=client
    )


def test_split_reference():
    assert split_reference("nginx") == ("nginx", "latest")
    assert split_reference("jellyfin/jellyfin:10.9") == ("jellyfin/jellyfin", "10.9")
    with pytest.raises(InvalidImageReferenceError):
        split_reference("bad ref")


def test_search_parses_and_caches(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"results": [
            {"repo_name": "jellyfin/jellyfin", "short_description": "Media",
             "star_count": 10, "pull_count": 1000, "is_official": True}
        ]})

    svc = _service(handler, HubCache(tmp_path / "hub.db"))
    r1 = svc.search_images("jellyfin")
    svc.search_images("jellyfin")
    assert r1.images[0].repo_name == "jellyfin/jellyfin"
    assert r1.images[0].is_official is True
    assert r1.stale is False
    assert calls["n"] == 1


def test_search_serves_stale_on_429(tmp_path):
    cache = HubCache(tmp_path / "hub.db")
    cache.set_search("jellyfin", json.dumps([{"repo_name": "old/img", "pull_count": 1}]))
    svc = _service(lambda r: httpx.Response(429), cache, ttl=-1)
    r = svc.search_images("jellyfin")
    assert r.stale is True
    assert r.fetched_at is not None
    assert r.images[0].repo_name == "old/img"


def test_search_429_without_cache_raises(tmp_path):
    svc = _service(lambda r: httpx.Response(429), HubCache(tmp_path / "hub.db"))
    with pytest.raises(HubUnavailableError, match="Limite de requisi"):
        svc.search_images("nothing")


def test_list_tags_official_uses_library(tmp_path):
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        return httpx.Response(200, json={"results": [
            {"name": "latest", "last_updated": "2026-01-01T00:00:00Z"}
        ]})

    svc = _service(handler, HubCache(tmp_path / "hub.db"))
    r = svc.list_tags("nginx")
    assert seen["path"] == "/v2/repositories/library/nginx/tags/"
    assert r.tags[0].name == "latest"


def test_list_tags_rejects_registry_host(tmp_path):
    svc = _service(lambda r: httpx.Response(200, json={"results": []}), HubCache(tmp_path / "hub.db"))
    with pytest.raises(InvalidImageReferenceError):
        svc.list_tags("ghcr.io/org/app")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dockerhub_service.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement the service**

In `app/services/dockerhub_service.py`:
- Pydantic models exactly as in Interfaces.
- Regexes: `REPO_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*$")`; `TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")`.
- `split_reference(ref)`: strip; if `@` present raise `InvalidImageReferenceError`; split at the last `:` only when no `/` follows it; default tag `latest`; validate repo with `REPO_RE`, tag with `TAG_RE`; raise `InvalidImageReferenceError` otherwise.
- `search_images(query)`: normalized key = `query.strip().lower()`; if empty return `HubSearchResult(images=[])`; read cache (`get_search`); if payload and not stale, parse and return with the cached `fetched_at`. Otherwise `GET /v2/search/repositories/` with `params={"query": q, "page_size": 25}`; on 200 parse `results`, `set_search`, return `stale=False` and `fetched_at=int(time.time())`; on any non-200/`httpx.HTTPError`, return cached payload with `stale=True` and the cached `fetched_at` if present, else raise `HubUnavailableError`.
- `list_tags(repo)`: normalize with `split_reference(repo)[0]`; reject refs whose first path segment contains `.` or `:` (registry host) with `InvalidImageReferenceError`; API repo = `repo` if `/` in it else `library/<repo>`; same cache/stale/fetched_at policy against `GET /v2/repositories/{api_repo}/tags/` with `params={"page_size": 25}`.
- Errors: `429` raises `HubUnavailableError("Limite de requisições do Docker Hub atingido. Tente novamente mais tarde.")` when there is no cached payload; any other non-200 or `httpx.HTTPError` raises `HubUnavailableError(f"Docker Hub indisponível: {exc}")`. Stale fallback wins over raising in both cases.
- Client: `self.client = client or httpx.Client(base_url=api_base, timeout=timeout)`; do not close a client passed in by the caller.
- Cache stores `json.dumps(results_list)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dockerhub_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/dockerhub_service.py tests/test_dockerhub_service.py
git commit -m "feat: add Docker Hub API client with cache and stale fallback"
```

---

### Task 4: Local images listing

**Files:**
- Modify: `app/services/docker_service.py`
- Test: `tests/test_docker_service.py`

**Interfaces:**
- Produces: model `ImageInfo(id, short_id, tags: list[str], size: int, created: str)`; `DockerService.list_images() -> list[ImageInfo]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_docker_service.py`:

```python
from app.services.docker_service import ImageInfo  # add to imports


def test_list_images():
    client = MagicMock()
    tagged = MagicMock()
    tagged.id = "sha256:abc"
    tagged.short_id = "abc"
    tagged.tags = ["nginx:alpine"]
    tagged.attrs = {"Size": 123, "Created": "2026-01-01T00:00:00Z"}
    dangling = MagicMock()
    dangling.id = "sha256:def"
    dangling.short_id = "def"
    dangling.tags = []
    dangling.attrs = {"Size": 50, "Created": "2026-01-02T00:00:00Z"}
    client.images.list.return_value = [tagged, dangling]

    images = DockerService(client=client).list_images()
    assert images[0].tags == ["nginx:alpine"]
    assert images[0].size == 123
    assert images[1].tags == []


def test_list_images_unavailable():
    client = MagicMock()
    client.images.list.side_effect = DockerException("socket missing")
    with pytest.raises(DockerUnavailableError):
        DockerService(client=client).list_images()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_docker_service.py -v`
Expected: FAIL (`ImportError: ImageInfo`).

- [ ] **Step 3: Implement `list_images`**

Add `ImageInfo` pydantic model and `DockerService.list_images()`: call `self._get_client().images.list()`, wrap `DockerException` as `DockerUnavailableError`, map each image to `ImageInfo(id=img.id, short_id=img.short_id, tags=list(img.tags or []), size=int(img.attrs.get("Size", 0)), created=img.attrs.get("Created", ""))`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_docker_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/docker_service.py tests/test_docker_service.py
git commit -m "feat: list local Docker images"
```

---

### Task 5: Starter compose, create stack, compose-up helper

**Files:**
- Modify: `app/services/compose_service.py`
- Test: `tests/test_compose_service.py`

**Interfaces:**
- Produces: `ComposeService(..., compose_up_timeout: int = 120, default_network: str = "stackpilot_net")`; `generate_starter_compose(image_ref: str) -> str`; `derive_service_name(image_ref: str) -> str`; `extract_images(compose_content: str) -> list[str]`; `create_stack(stack_name, compose_content, env_content=None) -> tuple[bool, str]`; `_run_compose_up(file_path) -> tuple[bool, str, bool]` (ok, output, cli_missing).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_compose_service.py`:

```python
import yaml


def test_generate_starter_compose():
    svc = ComposeService(docker_service=MagicMock(), default_network="stackpilot_net")
    data = yaml.safe_load(svc.generate_starter_compose("jellyfin/jellyfin:latest"))
    svc_def = data["services"]["jellyfin"]
    assert svc_def["image"] == "jellyfin/jellyfin:latest"
    assert "container_name" not in svc_def
    assert svc_def["networks"] == ["stackpilot_net"]
    assert data["networks"]["stackpilot_net"] == {"external": True}
    assert svc_def["restart"] == "unless-stopped"


def test_derive_service_name():
    svc = ComposeService(docker_service=MagicMock())
    assert svc.derive_service_name("nginx:alpine") == "nginx"
    assert svc.derive_service_name("jellyfin/jellyfin:latest") == "jellyfin"
    assert svc.derive_service_name("ghcr.io/org/app:1.2") == "app"
    assert svc.derive_service_name("redis@sha256:deadbeef") == "redis"
    assert svc.derive_service_name("sha256:0123456789abcdef") == "image-0123456789"


def test_extract_images():
    svc = ComposeService(docker_service=MagicMock())
    content = "services:\n  a:\n    image: nginx:latest\n  b:\n    image: redis:7\n"
    assert svc.extract_images(content) == ["nginx:latest", "redis:7"]


@patch("subprocess.run")
def test_create_stack_success(mock_subproc, tmp_path):
    mock_subproc.return_value = subprocess.CompletedProcess([], 0, "Started", "")
    svc = ComposeService(docker_service=MagicMock(), stacks_dir=tmp_path, compose_up_timeout=600)
    ok, msg = svc.create_stack("myapp", "services:\n  app:\n    image: nginx:latest\n")
    assert ok is True
    assert (tmp_path / "myapp" / "compose.yaml").is_file()


def test_create_stack_rejects_existing(tmp_path):
    (tmp_path / "myapp").mkdir()
    (tmp_path / "myapp" / "compose.yaml").write_text("keep", encoding="utf-8")
    svc = ComposeService(docker_service=MagicMock(), stacks_dir=tmp_path)
    ok, msg = svc.create_stack("myapp", "services:\n  app:\n    image: nginx:latest\n")
    assert ok is False
    assert "já existe" in msg
    assert (tmp_path / "myapp" / "compose.yaml").read_text(encoding="utf-8") == "keep"


def test_create_stack_rejects_traversal(tmp_path):
    svc = ComposeService(docker_service=MagicMock(), stacks_dir=tmp_path)
    ok, msg = svc.create_stack("../evil", "services:\n  app:\n    image: nginx:latest\n")
    assert ok is False
    assert not (tmp_path.parent / "evil").exists()


@patch("subprocess.run")
def test_create_stack_failure_removes_partial_dir(mock_subproc, tmp_path):
    mock_subproc.return_value = subprocess.CompletedProcess([], 1, "", "boom")
    svc = ComposeService(docker_service=MagicMock(), stacks_dir=tmp_path)
    ok, msg = svc.create_stack("myapp", "services:\n  app:\n    image: nginx:latest\n")
    assert ok is False
    assert not (tmp_path / "myapp").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_compose_service.py -v`
Expected: FAIL (`AttributeError: generate_starter_compose`).

- [ ] **Step 3: Implement the methods**

In `app/services/compose_service.py`:
- Add constructor kwargs `compose_up_timeout: int = 120` and `default_network: str = "stackpilot_net"`, stored as attributes.
- `STACK_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")`.
- `derive_service_name(image_ref)`: strip whitespace; if it starts with `sha256:`, return `"image-" + image_ref.removeprefix("sha256:")[:12]`; otherwise strip digest after `@`; drop tag after the last `:` when no `/` follows; take the path after the last `/`; lowercase; `re.sub(r"[^a-z0-9._-]", "-", name)`; if empty or starts with a digit, prepend `app-`.
- `generate_starter_compose(image_ref)`: return YAML via `yaml.safe_dump` of
  `{"services": {service: {"image": image_ref, "restart": "unless-stopped", "networks": [self.default_network]}}, "networks": {self.default_network: {"external": True}}}`.
- `extract_images(compose_content)`: `yaml.safe_load`, collect `str(svc["image"])` for dict services with an `image` key.
- `_run_compose_up(file_path)`: run `["docker", "compose", "-f", str(file_path), "up", "-d", "--remove-orphans"]` with `cwd=str(file_path.parent)` and `timeout=self.compose_up_timeout`; on `FileNotFoundError/OSError` retry with `["docker-compose", "-f", str(file_path), "up", "-d"]` (same `cwd`/`timeout`); return `(returncode == 0, combined_output, False)` on a run, `(False, "", True)` when both commands are missing.
- Refactor `deploy_compose` to call `_run_compose_up`; keep the existing docker-socket restart fallback only when `cli_missing` is `True`. The success/failure message keeps the existing shape: success `"Stack implantada com sucesso!\n" + output`, failure `"Falha ao executar 'docker compose up':\n" + output`.
- `create_stack(stack_name, compose_content, env_content=None)`:
  1. `name = stack_name.strip().lower()`; reject with `(False, "Nome de stack inválido...")` if not `STACK_NAME_RE`.
  2. `validate_compose_yaml`; return `(False, err)` on failure.
  3. `base = self._resolve_stacks_dir().resolve()`; `target = (base / name).resolve()`; return `(False, ...)` if `base` not in `target.parents`.
  4. If `target.exists()`: return `(False, "A stack '<name>' já existe...")`.
  5. `target.mkdir(parents=True)`; write `compose.yaml`; write `.env` when `env_content` is non-empty.
  6. `ok, output, missing = self._run_compose_up(file_path)`; on success return `(True, ...)`; on failure `shutil.rmtree(target)` (best effort) and return `(False, ...)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_compose_service.py -v`
Expected: PASS (existing tests included).

- [ ] **Step 5: Commit**

```bash
git add app/services/compose_service.py tests/test_compose_service.py
git commit -m "feat: generate starter compose and create Docker stacks"
```

---

### Task 6: Docker page, wiring, Images (local/used) and Containers tabs

**Files:**
- Modify: `app/dependencies.py`
- Modify: `app/main.py`
- Create: `app/routers/docker.py`
- Create: `app/templates/docker.html`
- Create: `app/templates/partials/image_list.html`
- Test: `tests/test_docker_router.py`

**Interfaces:**
- Produces: `get_hub_cache() -> HubCache`, `get_dockerhub_service() -> DockerHubService`; `get_compose_service()` passes the new timeout/network kwargs; `GET /docker` (context: `user`, `images`, `used_images`, `containers`, `images_error`, `containers_error`) and `GET /docker/images` (context: `images`, `used_images`, `images_error`).

- [ ] **Step 1: Write the failing tests**

`tests/test_docker_router.py`:

```python
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.dependencies import get_docker_service, get_hub_cache
from app.main import app
from app.services.docker_service import ContainerInfo, ImageInfo
from app.services.hub_cache import UsedImage


def _client():
    c = TestClient(app)
    c.post("/login", data={"username": "admin", "password": "admin"})
    return c


def test_docker_page_renders_images_and_containers():
    mock_docker = MagicMock()
    mock_docker.list_images.return_value = [
        ImageInfo(id="sha256:abc", short_id="abc", tags=["nginx:alpine"], size=48, created="2026-01-01")
    ]
    mock_docker.list_containers.return_value = [
        ContainerInfo(id="c1", short_id="c1", name="web", image="nginx", status="running")
    ]
    mock_cache = MagicMock()
    mock_cache.list_used_images.return_value = [
        UsedImage(image="redis:7", last_used_at=1, use_count=1, stack_name="cache")
    ]
    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    app.dependency_overrides[get_hub_cache] = lambda: mock_cache
    try:
        r = _client().get("/docker")
        assert r.status_code == 200
        assert "Images" in r.text and "Containers" in r.text
        assert "nginx:alpine" in r.text
        assert "redis:7" in r.text
        assert "web" in r.text
    finally:
        app.dependency_overrides.clear()


def test_docker_page_renders_dangling_image():
    mock_docker = MagicMock()
    mock_docker.list_images.return_value = [
        ImageInfo(id="sha256:def", short_id="def", tags=[], size=50, created="2026-01-02")
    ]
    mock_docker.list_containers.return_value = []
    mock_cache = MagicMock()
    mock_cache.list_used_images.return_value = []
    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    app.dependency_overrides[get_hub_cache] = lambda: mock_cache
    try:
        r = _client().get("/docker")
        assert r.status_code == 200
        assert "sha256:def" in r.text
    finally:
        app.dependency_overrides.clear()


def test_docker_images_partial_renders_used_images():
    mock_docker = MagicMock()
    mock_docker.list_images.return_value = []
    mock_cache = MagicMock()
    mock_cache.list_used_images.return_value = [
        UsedImage(image="redis:7", last_used_at=1, use_count=1, stack_name="cache")
    ]
    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    app.dependency_overrides[get_hub_cache] = lambda: mock_cache
    try:
        r = _client().get("/docker/images")
        assert r.status_code == 200
        assert "redis:7" in r.text
    finally:
        app.dependency_overrides.clear()


def test_docker_page_requires_auth():
    client = TestClient(app)
    for path in ("/docker", "/docker/images"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_docker_router.py -v`
Expected: FAIL (`get_hub_cache` import error / 404).

- [ ] **Step 3: Implement wiring, route, and templates**

`app/dependencies.py`:
- Add `_resolve_hub_db_path(configured: Path) -> Path`: try `configured.parent.mkdir(parents=True, exist_ok=True)` and `os.access(parent, os.W_OK)`; else fall back to `Path.cwd() / "data" / "stackpilot.db"` (creating `data/`).
- `get_hub_cache()` → `HubCache(_resolve_hub_db_path(get_settings().hub_db_path))`.
- `get_dockerhub_service()` → `DockerHubService(cache=get_hub_cache(), ttl_seconds=..., api_base=..., timeout=...)`.
- Update `get_compose_service()` to pass `compose_up_timeout=settings.compose_up_timeout_seconds` and `default_network=settings.stackpilot_network`.

`app/main.py`: import `docker as docker_router` from `app.routers` and `app.include_router(docker_router.router)`.

`app/routers/docker.py`: create `router = APIRouter(tags=["docker"])` with `GET /docker` and `GET /docker/images`. Both fetch `docker_svc.list_images()` and `hub_cache.list_used_images()` (catching `DockerUnavailableError` into `images_error`); `GET /docker` also fetches `docker_svc.list_containers()` (catching into `containers_error`).

`app/templates/docker.html`: extend `base.html` (`{% block content %}`); compact header with links to `/` and `/docker` plus logout; a tab bar with "Images" (active) and "Containers"; an Images pane containing `<div id="image-list">{% include "partials/image_list.html" %}</div>` plus `<div id="image-detail"></div>`; a Containers pane containing `<div id="container-list">{% include "partials/container_list.html" %}</div>`, `<div id="container-compose"></div>`, `<div id="container-logs"></div>`. Tab switching may be plain JS toggling Tailwind `hidden` classes (as in `container_compose.html`).

`app/templates/partials/image_list.html`: render `images_error`; render `used_images`; render local images grouped by tag (loop tags, or id when no tags). Display-only in this task.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_docker_router.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/dependencies.py app/main.py app/routers/docker.py app/templates/docker.html app/templates/partials/image_list.html tests/test_docker_router.py
git commit -m "feat: add Docker Desktop-style page with images and containers tabs"
```

---

### Task 7: Docker Hub search and tag endpoints

**Files:**
- Modify: `app/routers/docker.py`
- Modify: `app/templates/partials/image_list.html`
- Create: `app/templates/partials/hub_search.html`
- Create: `app/templates/partials/hub_tags.html`
- Test: `tests/test_docker_router.py`

**Interfaces:**
- Produces: `GET /hub/search?q=str` → `partials/hub_search.html` with `{query, results: HubSearchResult | None, error}`; `GET /hub/tags?repo=str` → `partials/hub_tags.html` with `{repo, result: HubTagsResult | None, error}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_docker_router.py`:

```python
from app.dependencies import get_dockerhub_service
from app.services.dockerhub_service import HubImage, HubSearchResult, HubTag, HubTagsResult, HubUnavailableError


def test_hub_search_renders_results():
    mock_hub = MagicMock()
    mock_hub.search_images.return_value = HubSearchResult(
        images=[HubImage(repo_name="jellyfin/jellyfin", pull_count=1000, is_official=True)]
    )
    app.dependency_overrides[get_dockerhub_service] = lambda: mock_hub
    try:
        r = _client().get("/hub/search?q=jellyfin")
        assert r.status_code == 200
        assert "jellyfin/jellyfin" in r.text
    finally:
        app.dependency_overrides.clear()


def test_hub_search_no_results():
    mock_hub = MagicMock()
    mock_hub.search_images.return_value = HubSearchResult(images=[])
    app.dependency_overrides[get_dockerhub_service] = lambda: mock_hub
    try:
        r = _client().get("/hub/search?q=zzzz")
        assert r.status_code == 200
        assert "Nenhuma imagem" in r.text
    finally:
        app.dependency_overrides.clear()


def test_hub_search_error_shows_message():
    mock_hub = MagicMock()
    mock_hub.search_images.side_effect = HubUnavailableError("limite de requisições")
    app.dependency_overrides[get_dockerhub_service] = lambda: mock_hub
    try:
        r = _client().get("/hub/search?q=jellyfin")
        assert r.status_code == 200
        assert "limite de requisições" in r.text
    finally:
        app.dependency_overrides.clear()


def test_hub_tags_renders():
    mock_hub = MagicMock()
    mock_hub.list_tags.return_value = HubTagsResult(
        repo="jellyfin/jellyfin", tags=[HubTag(name="latest")]
    )
    app.dependency_overrides[get_dockerhub_service] = lambda: mock_hub
    try:
        r = _client().get("/hub/tags?repo=jellyfin/jellyfin")
        assert r.status_code == 200
        assert "latest" in r.text
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_docker_router.py -v`
Expected: FAIL (404 on `/hub/search`).

- [ ] **Step 3: Implement endpoints and templates**

`app/routers/docker.py`: add the two GET endpoints. `/hub/search` runs search only when `q.strip()` is non-empty; catch `HubUnavailableError` into `error`. `/hub/tags` catches `HubUnavailableError` and `InvalidImageReferenceError` into `error`.

`image_list.html`: add a search form at the top — `hx-get="/hub/search" hx-target="#hub-results" hx-include="closest form"`, an input named `q`, and `<div id="hub-results"></div>`.

`hub_search.html`: if `error`, show it; if `results is none`, render nothing (empty query); if `results.stale`, show a "cache — pode estar desatualizado" badge; if `results.images` is empty, show "Nenhuma imagem encontrada"; otherwise list each image's `repo_name`, `short_description`, `pull_count`, and an `is_official` badge. Display-only in this task.

`hub_tags.html`: show `error`, or the repo name and its `tags` (name). Display-only in this task.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_docker_router.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/routers/docker.py app/templates/partials/image_list.html app/templates/partials/hub_search.html app/templates/partials/hub_tags.html tests/test_docker_router.py
git commit -m "feat: search Docker Hub and list image tags from the panel"
```

---

### Task 8: Compose editor and create-container flow

**Files:**
- Modify: `app/routers/docker.py`
- Modify: `app/templates/partials/image_list.html`
- Modify: `app/templates/partials/hub_search.html`
- Modify: `app/templates/partials/hub_tags.html`
- Create: `app/templates/partials/create_compose.html`
- Create: `app/templates/partials/create_result.html`
- Test: `tests/test_docker_router.py`

**Interfaces:**
- Produces: `GET /docker/compose?image=str` → `partials/create_compose.html` with `{image, stack_name, compose_content, env_content, error, success, output}`; `POST /docker/create` (form `stack_name`, `image`, `compose_content`, `env_content`) → `partials/create_result.html` on success (`{message, stack_name}`) or `partials/create_compose.html` on failure (same context with `error`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_docker_router.py`:

```python
from app.dependencies import get_compose_service


def test_compose_editor_prefills():
    mock_compose = MagicMock()
    mock_compose.generate_starter_compose.return_value = "services:\n  jellyfin:\n    image: jellyfin/jellyfin:latest\n"
    mock_compose.derive_service_name.return_value = "jellyfin"
    app.dependency_overrides[get_compose_service] = lambda: mock_compose
    try:
        r = _client().get("/docker/compose?image=jellyfin/jellyfin:latest")
        assert r.status_code == 200
        assert "image: jellyfin/jellyfin:latest" in r.text
        assert 'value="jellyfin"' in r.text
    finally:
        app.dependency_overrides.clear()


def test_create_success_records_used_images():
    mock_compose = MagicMock()
    mock_compose.create_stack.return_value = (True, "Stack criada")
    mock_compose.extract_images.return_value = ["jellyfin/jellyfin:latest"]
    mock_cache = MagicMock()
    app.dependency_overrides[get_compose_service] = lambda: mock_compose
    app.dependency_overrides[get_hub_cache] = lambda: mock_cache
    try:
        r = _client().post(
            "/docker/create",
            data={"stack_name": "jellyfin", "image": "jellyfin/jellyfin:latest",
                  "compose_content": "services:\n  jellyfin:\n    image: jellyfin/jellyfin:latest\n",
                  "env_content": ""},
        )
        assert r.status_code == 200
        assert "Stack criada" in r.text
        mock_cache.record_used_image.assert_called_once_with("jellyfin/jellyfin:latest", "jellyfin")
    finally:
        app.dependency_overrides.clear()


def test_create_failure_preserves_compose():
    mock_compose = MagicMock()
    mock_compose.create_stack.return_value = (False, "falha no deploy")
    app.dependency_overrides[get_compose_service] = lambda: mock_compose
    app.dependency_overrides[get_hub_cache] = lambda: MagicMock()
    try:
        r = _client().post(
            "/docker/create",
            data={"stack_name": "jellyfin", "image": "jellyfin/jellyfin:latest",
                  "compose_content": "services:\n  jellyfin:\n    image: jellyfin/jellyfin:latest\n",
                  "env_content": ""},
        )
        assert r.status_code == 200
        assert "falha no deploy" in r.text
        assert "image: jellyfin/jellyfin:latest" in r.text
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_docker_router.py -v`
Expected: FAIL (404 on `/docker/compose`).

- [ ] **Step 3: Implement endpoints and templates**

`app/routers/docker.py`: add `GET /docker/compose` and `POST /docker/create`. `GET` builds `compose_content = compose_svc.generate_starter_compose(image)` and `stack_name = compose_svc.derive_service_name(image)`. `POST` calls `compose_svc.create_stack(stack_name, compose_content, env_content)`; on success loop `compose_svc.extract_images(compose_content)` calling `hub_cache.record_used_image(img, stack_name)` and render `create_result.html`; on failure render `create_compose.html` with `error`.

Add the action buttons (this task):
- `image_list.html`: each tag row gets `hx-get="/docker/compose?image={{ tag }}" hx-target="#image-detail" hx-swap="innerHTML"`; dangling row uses `{{ img.id }}`.
- `hub_search.html`: each result gets a "Tags" button `hx-get="/hub/tags?repo={{ image.repo_name }}" hx-target="#image-detail"`.
- `hub_tags.html`: each tag gets a "Criar" button `hx-get="/docker/compose?image={{ repo }}:{{ tag.name }}" hx-target="#image-detail"`.

`create_compose.html`: root `<div>` **without** an `id` (it replaces the inner HTML of `#image-detail`); a form `hx-post="/docker/create" hx-target="#image-detail" hx-swap="innerHTML"` containing a hidden `image`, a `stack_name` input (value `stack_name`), a `compose_content` textarea, an `env_content` textarea, an error block, and a submit button "Implantar".

`create_result.html`: success message plus a note that the container is available under the Containers tab.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_docker_router.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/routers/docker.py app/templates/partials/image_list.html app/templates/partials/hub_search.html app/templates/partials/hub_tags.html app/templates/partials/create_compose.html app/templates/partials/create_result.html tests/test_docker_router.py
git commit -m "feat: edit generated compose and create containers from the panel"
```

---

### Task 9: Navigation, persistent volume, docs

**Files:**
- Modify: `app/templates/dashboard.html`
- Modify: `docker-compose.yml`
- Modify: `.gitignore`
- Modify: `README.md`
- Test: `tests/test_routers.py`, `tests/test_deployment_assets.py`

**Interfaces:** none (wiring and docs).

- [ ] **Step 1: Write the failing tests**

In `tests/test_routers.py`, extend `test_dashboard_renders_routes_with_base_domain` (or add a new test) to assert `'href="/docker"'` appears in the dashboard HTML.

In `tests/test_deployment_assets.py`:

```python
def test_root_compose_mounts_data_volume():
    data = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    volumes = data["services"]["stackpilot"]["volumes"]
    assert "./data:/opt/stackpilot" in volumes


def test_readme_documents_docker_hub():
    assert "Docker Hub" in Path("README.md").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_routers.py tests/test_deployment_assets.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement navigation, volume, and docs**

- `dashboard.html`: add a sidebar link in the "Docker & Stacks" group pointing to `/docker` (label "Docker").
- `docker-compose.yml`: add `- ./data:/opt/stackpilot` to the `stackpilot` service `volumes`.
- `.gitignore`: add `data/`.
- `README.md`: mention the Docker Hub search/create feature and the new env vars (`HUB_DB_PATH`, `HUB_CACHE_TTL_SECONDS`, `COMPOSE_UP_TIMEOUT_SECONDS`, `STACKPILOT_NETWORK`).

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `pytest -q`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add app/templates/dashboard.html docker-compose.yml .gitignore README.md tests/test_routers.py tests/test_deployment_assets.py
git commit -m "feat: link Docker view and persist cache volume"
```

---

## Self-Review Notes

- **Spec coverage:** search (Task 3/7), tags (Task 3/7), cache + TTL + stale + `fetched_at` (Task 2/3), used images (Task 2/6/8), local images (Task 4/6), starter compose + create stack (Task 5/8), Docker Desktop tabs (Task 6), network/timeout/persistence (Task 1/5/9), auth on new routes (Task 6), security validation (Task 3/5), `/docker/images` (Task 6), dangling image handling (Task 4/5/6/8).
- **Deliberate deviations from the spec:** `/docker/compose?image=` replaces `/hub/compose?repo=&tag=` so Hub, local, and dangling images share one editor; `generate_starter_compose(image_ref)` takes the full reference instead of `(repo, tag)`; `HubCache.__init__` calls `init_db()` instead of a module-level `init_db(path)`; `UsedImage` lives in `hub_cache.py`.
- **Types:** `HubSearchResult.images`, `HubTagsResult.tags`, `ImageInfo.tags`, `UsedImage.image`, and `fetched_at` are used consistently across tasks; `_run_compose_up` keeps `cwd=file_path.parent` so relative compose paths still resolve.
- **Review Focus** lines each name a test in the owning task (see section above).
- **Baseline:** `52 passed` with `.venv\Scripts\python.exe -m pytest -q` before Task 1.
