# Background Tasks List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated `/tasks` page backed by SQLite so users can trigger long-running Docker/Compose actions without blocking HTTP requests and track each task's title and status (`running`, `completed`, `failed`).

**Architecture:** A `TaskService` persists task records in `stackpilot.db` (`tasks` table) and runs each action via `asyncio.create_task`, updating status on completion or failure. On app startup, any leftover `running` tasks are marked `failed`. A `/tasks` router serves the page and an HTMX-polled partial (`/tasks/list`).

**Tech Stack:** FastAPI, SQLite (`sqlite3`), `asyncio`, Jinja2, HTMX, TailwindCSS, pytest.

**Spec:** `docs/superpowers/specs/2026-11-20-background-tasks-design.md`

## Global Constraints

- Persist tasks in `stackpilot.db` (same DB resolution pattern as `hub_cache.py`).
- On startup, mark any `running` tasks as `failed`.
- Dedicated `/tasks` page displays only the task title and its status (`running`, `completed`, `failed`) — no detailed logs or percentage progress bars.
- All endpoints require authentication (`require_auth`).

## Review Focus

- Interrupted tasks: server restarts while a task is `running` -> `mark_interrupted_tasks()` marks it `failed` with `finished_at` set.
- Sync blocking functions passed to `enqueue` (e.g., Docker SDK calls): must run via `asyncio.to_thread` or coroutine wrapper so the event loop is not blocked.
- Failing background task: exception raised inside the task must be caught, logged, and update status to `failed` without crashing the event loop.
- Empty task list: `/tasks/list` renders a clean empty state without errors.
- Unauthenticated access: `GET /tasks` and `GET /tasks/list` redirect/reject when not logged in.

---

### Task 1: `TaskService` & SQLite Persistence

**Files:**
- Create: `app/services/task_service.py`
- Test: `tests/test_task_service.py`

**Interfaces:**
- Produces:
  - `TaskRecord` dataclass: `id: str`, `title: str`, `status: str`, `created_at: str`, `finished_at: str | None`
  - `TaskService(db_path: Path)`:
    - `init_db() -> None`
    - `mark_interrupted_tasks() -> int`
    - `enqueue(title: str, fn: Callable[[], Any]) -> TaskRecord` (supports both sync callables via `asyncio.to_thread` and async callables/coroutines)
    - `list_tasks(limit: int = 50) -> list[TaskRecord]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_task_service.py` with tests:
- `test_enqueue_sync_task_completes(tmp_path)`: enqueues a sync function, awaits `asyncio.sleep(0.05)`, asserts `list_tasks()` has 1 task with `status == "completed"` and `finished_at is not None`.
- `test_enqueue_failing_task_marks_failed(tmp_path)`: enqueues a function that raises `RuntimeError("boom")`, awaits `asyncio.sleep(0.05)`, asserts `status == "failed"` and `finished_at is not None`.
- `test_mark_interrupted_tasks(tmp_path)`: inserts a `running` task directly, calls `mark_interrupted_tasks()`, asserts it returns `1` and the task now has `status == "failed"`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_task_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.task_service'`

- [ ] **Step 3: Implement `TaskService` in `app/services/task_service.py`**

Implement `TaskRecord` and `TaskService` using `sqlite3` with `CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, finished_at TEXT)`. Keep a `self._background_tasks: set[asyncio.Task]` to prevent GC of running tasks.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_task_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/task_service.py tests/test_task_service.py
git commit -m "feat: add TaskService with SQLite persistence"
```

---

### Task 2: Dependency & Lifespan Wiring

**Files:**
- Modify: `app/dependencies.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `TaskService` from `app.services.task_service`
- Produces: `get_task_service(request: Request) -> TaskService` in `app/dependencies.py`

- [ ] **Step 1: Add `get_task_service` to `app/dependencies.py`**

Store/retrieve `TaskService(_resolve_db_path(get_settings().hub_db_path))` on `request.app.state.task_service` (same pattern as `get_metrics_collector`).

- [ ] **Step 2: Initialize `TaskService` in `app/main.py` lifespan**

In `lifespan(app: FastAPI)`, instantiate `TaskService`, call `init_db()` and `mark_interrupted_tasks()`, and assign `app.state.task_service = task_service`.

- [ ] **Step 3: Run existing tests to verify no regressions**

Run: `pytest tests/test_dependencies.py tests/test_routers.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add app/dependencies.py app/main.py
git commit -m "feat: wire TaskService into dependencies and app lifespan"
```

---

### Task 3: `/tasks` Router, Templates & Navigation

**Files:**
- Create: `app/routers/tasks.py`
- Create: `app/templates/tasks.html`
- Create: `app/templates/partials/task_list.html`
- Modify: `app/main.py` (include `tasks.router`)
- Modify: `app/templates/dashboard.html`, `app/templates/docker.html`, `app/templates/settings.html` (add "Tarefas" nav link)
- Test: `tests/test_tasks_router.py`

**Interfaces:**
- Consumes: `get_task_service`, `require_auth`, `templates`
- Produces: `GET /tasks`, `GET /tasks/list`

- [ ] **Step 1: Write the failing router tests**

Create `tests/test_tasks_router.py`:
- `test_tasks_page_requires_auth(client)`: `GET /tasks` without session returns 401/303.
- `test_tasks_page_renders(auth_client)`: `GET /tasks` returns 200 and contains `"Tarefas"`.
- `test_tasks_list_partial_renders_tasks(auth_client, app)`: enqueues/inserts a task, `GET /tasks/list` returns 200 with the task title and status badge.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tasks_router.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `app/routers/tasks.py`, `tasks.html`, `partials/task_list.html`, and register router**

In `task_list.html`, render each task's `title` and `status` badge (`running` -> Em andamento, `completed` -> Concluída, `failed` -> Falhou). In `tasks.html`, include `hx-get="/tasks/list" hx-trigger="load, every 2s" hx-swap="innerHTML"`. Add the `/tasks` link to the navigation bar in `dashboard.html`, `docker.html`, and `settings.html`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tasks_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/tasks.py app/templates/tasks.html app/templates/partials/task_list.html app/main.py app/templates/dashboard.html app/templates/docker.html app/templates/settings.html tests/test_tasks_router.py
git commit -m "feat: add /tasks page and HTMX polling partial"
```

---

### Task 4: Integrate Long-Running Actions with `TaskService`

**Files:**
- Modify: `app/routers/docker.py` (image pull, image remove)
- Modify: `app/routers/containers.py` (compose up/down, container create/remove)
- Test: `tests/test_docker_router.py`, `tests/test_routers.py`

**Interfaces:**
- Consumes: `get_task_service` (`TaskService.enqueue`)

- [ ] **Step 1: Update `app/routers/docker.py` pull/remove endpoints to enqueue via `TaskService`**

Wrap long-running `docker_svc.pull_image` and `docker_svc.remove_image` calls in `task_svc.enqueue(f"Pull da imagem {image_ref}", ...)` and return immediate HTMX feedback with a link to `/tasks`.

- [ ] **Step 2: Update `app/routers/containers.py` compose/create/remove endpoints to enqueue via `TaskService`**

Wrap `compose_svc.up`, `compose_svc.down`, `docker_svc.create_container`, `docker_svc.remove_container` in `task_svc.enqueue(...)` and return immediate HTMX feedback.

- [ ] **Step 3: Run full test suite**

Run: `pytest -v`
Expected: PASS (update any existing router tests that asserted synchronous execution if needed).

- [ ] **Step 4: Commit**

```bash
git add app/routers/docker.py app/routers/containers.py tests/test_docker_router.py tests/test_routers.py
git commit -m "feat: run long Docker and Compose actions as background tasks"
```
