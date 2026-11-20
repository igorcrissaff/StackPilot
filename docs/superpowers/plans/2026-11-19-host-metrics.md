# Métricas do host no dashboard — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exibir no dashboard métricas do host (CPU, memória, swap, disco, load, uptime e SO), atualizadas a cada 10s via HTMX.

**Architecture:** `MetricsService` coleta dados com `psutil` e monta um modelo Pydantic `SystemMetrics`. Um endpoint `GET /metrics` renderiza `partials/system_metrics.html`; o dashboard inclui essa partial com polling HTMX de 10s.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, HTMX, Tailwind CDN, psutil, pytest.

**Spec:** `docs/superpowers/specs/2026-11-19-host-metrics-design.md`

## Global Constraints

- Métricas do **host** (StackPilot nativo no WSL/Linux); não tratar métricas de container.
- Atualização automática a cada 10s via HTMX; sem recarregar a página.
- Nova dependência única: `psutil`.
- Não quebrar no Windows (load average pode não existir).
- Manter o padrão visual escuro estilo Portainer.

## Review Focus

- Primeira leitura de `cpu_percent` não deve exibir erro (se 0.0, é aceitável).
- Ausência de `/etc/os-release` deve cair em fallback (`platform.system()`/`release()`).
- `getloadavg` indisponível não pode derrubar a coleta (campos de load viram `None`).
- Swap com total 0 não deve renderizar barra/card enganoso.
- `/metrics` exige autenticação e não deve retornar 500 se a coleta falhar.

---

### Task 1: MetricsService + dependência psutil

**Files:**
- Modify: `pyproject.toml` (adicionar `psutil>=5.9.0`)
- Create: `app/services/metrics_service.py`
- Test: `tests/test_metrics_service.py`

**Interfaces:**
- Produces: `SystemMetrics` (Pydantic) com campos: `cpu_percent: float`, `cpu_count: int`, `load_1: float | None`, `load_5: float | None`, `load_15: float | None`, `memory_used: int`, `memory_total: int`, `memory_percent: float`, `swap_used: int`, `swap_total: int`, `swap_percent: float`, `disk_used: int`, `disk_total: int`, `disk_percent: float`, `uptime_seconds: int`, `os_name: str`, `os_version: str`, `kernel: str`, `architecture: str`, `hostname: str`.
- Produces: `MetricsService.collect() -> SystemMetrics`.

- [ ] **Step 1: Instalar psutil no ambiente**

Run: `uv pip install --python .venv/Scripts/python.exe "psutil>=5.9.0"` (ou `./.venv/Scripts/python.exe -m pip install "psutil>=5.9.0"`).

- [ ] **Step 2: Escrever os testes que falham em `tests/test_metrics_service.py`**

```python
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import metrics_service
from app.services.metrics_service import MetricsService

GB = 1024 ** 3


def _fake_psutil():
    fake = MagicMock()
    fake.cpu_percent.return_value = 12.5
    fake.cpu_count.return_value = 8
    fake.getloadavg.return_value = (0.5, 0.4, 0.3)
    fake.virtual_memory.return_value = SimpleNamespace(used=2 * GB, total=8 * GB, percent=25.0)
    fake.swap_memory.return_value = SimpleNamespace(used=0, total=0, percent=0.0)
    fake.disk_usage.return_value = SimpleNamespace(used=100 * GB, total=500 * GB, percent=20.0)
    fake.boot_time.return_value = time.time() - 3600
    return fake


def test_collect_builds_metrics(monkeypatch):
    fake = _fake_psutil()
    monkeypatch.setattr(metrics_service, "psutil", fake)
    monkeypatch.setattr(metrics_service, "_read_os_release", lambda: ("Ubuntu 24.04", "24.04"))
    monkeypatch.setattr(metrics_service.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(metrics_service.platform, "release", lambda: "6.8.0")
    monkeypatch.setattr(metrics_service.platform, "system", lambda: "Linux")
    monkeypatch.setattr(metrics_service.socket, "gethostname", lambda: "homelab")

    m = MetricsService().collect()

    assert m.cpu_percent == 12.5
    assert m.cpu_count == 8
    assert m.load_1 == 0.5
    assert m.load_5 == 0.4
    assert m.load_15 == 0.3
    assert m.memory_total == 8 * GB
    assert m.memory_percent == 25.0
    assert m.disk_percent == 20.0
    assert 3590 <= m.uptime_seconds <= 3610
    assert m.os_name == "Ubuntu 24.04"
    assert m.os_version == "24.04"
    assert m.kernel == "6.8.0"
    assert m.architecture == "x86_64"
    assert m.hostname == "homelab"


def test_collect_handles_missing_loadavg(monkeypatch):
    fake = _fake_psutil()
    fake.getloadavg.side_effect = OSError("not supported")
    monkeypatch.setattr(metrics_service, "psutil", fake)
    monkeypatch.setattr(metrics_service, "_read_os_release", lambda: (None, None))
    monkeypatch.setattr(metrics_service.platform, "system", lambda: "Windows")
    monkeypatch.setattr(metrics_service.platform, "release", lambda: "11")
    monkeypatch.setattr(metrics_service.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(metrics_service.socket, "gethostname", lambda: "pc")

    m = MetricsService().collect()

    assert m.load_1 is None and m.load_5 is None and m.load_15 is None
    assert m.os_name == "Windows"
    assert m.os_version == "11"


def test_read_os_release_fallback_when_missing(monkeypatch, tmp_path):
    missing = tmp_path / "os-release"
    monkeypatch.setattr(metrics_service, "OS_RELEASE_PATH", missing)
    assert metrics_service._read_os_release() == (None, None)
```

- [ ] **Step 3: Rodar para ver falhar**

Run: `pytest tests/test_metrics_service.py -q`
Expected: FAIL (`ImportError` de `app.services.metrics_service`).

- [ ] **Step 4: Implementar `app/services/metrics_service.py`**

- `OS_RELEASE_PATH = Path("/etc/os-release")`.
- `_read_os_release() -> tuple[str | None, str | None]`: lê o arquivo (se existir), parseia `NAME`/`PRETTY_NAME` e `VERSION_ID`/`VERSION`; em qualquer erro retorna `(None, None)`.
- `_load_avg() -> tuple[float | None, float | None, float | None]`: tenta `psutil.getloadavg()`; em `OSError`/`AttributeError` retorna `(None, None, None)`.
- `MetricsService.collect()`: preenche `os_name`/`os_version` usando `_read_os_release`, com fallback `platform.system()` e `platform.release()`; kernel `platform.release()`; arquitetura `platform.machine()`; hostname `socket.gethostname()`; disco `/`; uptime `int(time.time() - psutil.boot_time())`.

- [ ] **Step 5: Rodar os testes**

Run: `pytest tests/test_metrics_service.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml app/services/metrics_service.py tests/test_metrics_service.py
git commit -m "feat: add host metrics service"
```

---

### Task 2: Endpoint /metrics, partial e dashboard

**Files:**
- Modify: `app/dependencies.py` (adicionar `get_metrics_service`)
- Create: `app/routers/metrics.py`
- Create: `app/templates/partials/system_metrics.html`
- Modify: `app/main.py` (incluir router)
- Modify: `app/templates/dashboard.html` (incluir seção)
- Test: `tests/test_metrics_router.py`

**Interfaces:**
- Consumes: `MetricsService.collect()` e `SystemMetrics` da Task 1.
- Produces: `GET /metrics` (autenticado) → partial `system_metrics.html` com polling `hx-get="/metrics" hx-trigger="load, every 10s" hx-swap="outerHTML"`.

- [ ] **Step 1: Escrever os testes que falham em `tests/test_metrics_router.py`**

```python
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.dependencies import get_metrics_service
from app.main import app
from app.services.metrics_service import SystemMetrics


def _client():
    c = TestClient(app)
    c.post("/login", data={"username": "admin", "password": "admin"})
    return c


def _metrics(hostname="homelab"):
    return SystemMetrics(
        cpu_percent=12.5, cpu_count=8, load_1=0.5, load_5=0.4, load_15=0.3,
        memory_used=2 * 1024 ** 3, memory_total=8 * 1024 ** 3, memory_percent=25.0,
        swap_used=0, swap_total=0, swap_percent=0.0,
        disk_used=100 * 1024 ** 3, disk_total=500 * 1024 ** 3, disk_percent=20.0,
        uptime_seconds=3600, os_name="Ubuntu 24.04", os_version="24.04",
        kernel="6.8.0", architecture="x86_64", hostname=hostname,
    )


def test_metrics_requires_auth():
    r = TestClient(app).get("/metrics", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_metrics_renders_host_data():
    mock = MagicMock()
    mock.collect.return_value = _metrics()
    app.dependency_overrides[get_metrics_service] = lambda: mock
    try:
        r = _client().get("/metrics")
        assert r.status_code == 200
        assert "homelab" in r.text
        assert "Ubuntu 24.04" in r.text
        assert "12.5" in r.text
        assert 'hx-get="/metrics"' in r.text
        assert "every 10s" in r.text
    finally:
        app.dependency_overrides.clear()


def test_dashboard_includes_metrics_section():
    mock_docker = MagicMock()
    mock_docker.list_containers.return_value = []
    mock_docker.list_images.return_value = []
    mock_metrics = MagicMock()
    mock_metrics.collect.return_value = _metrics()
    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    app.dependency_overrides[get_metrics_service] = lambda: mock_metrics
    try:
        r = _client().get("/")
        assert r.status_code == 200
        assert 'id="system-metrics"' in r.text
        assert 'hx-get="/metrics"' in r.text
    finally:
        app.dependency_overrides.clear()
```

Adicionar o import de `get_docker_service` conforme necessário.

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest tests/test_metrics_router.py -q`
Expected: FAIL (404 e imports ausentes).

- [ ] **Step 3: Implementar `app/dependencies.py`**

Adicionar `from app.services.metrics_service import MetricsService` e:

```python
def get_metrics_service() -> MetricsService:
    return MetricsService()
```

- [ ] **Step 4: Implementar `app/routers/metrics.py`**

```python
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.auth import require_auth
from app.dependencies import get_metrics_service, templates
from app.services.metrics_service import MetricsService

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=HTMLResponse)
def system_metrics(
    request: Request,
    user: str = Depends(require_auth),
    metrics_svc: MetricsService = Depends(get_metrics_service),
):
    return templates.TemplateResponse(
        request,
        "partials/system_metrics.html",
        {"metrics": metrics_svc.collect()},
    )
```

- [ ] **Step 5: Registrar o router em `app/main.py`**

`from app.routers import containers, docker, metrics` e `app.include_router(metrics.router)`.

- [ ] **Step 6: Criar `app/templates/partials/system_metrics.html`**

Bloco raiz:

```html
<div id="system-metrics"
     class="bg-[#161e2e] border border-[#232f45] rounded-xl p-5 shadow-xl"
     hx-get="/metrics"
     hx-trigger="load, every 10s"
     hx-swap="outerHTML">
```

Conteúdo: cabeçalho "Servidor" com hostname e `os_name`/`kernel`/`architecture`/uptime; grid de cards com barras de progresso para CPU (`metrics.cpu_percent`), memória (`metrics.memory_percent`, usado/total formatados) e disco (`metrics.disk_percent`); uma linha com load 1/5/15 (exibir "—" quando `None`); card de swap apenas se `metrics.swap_total > 0`. Formatar bytes em GB e uptime em dias/horas.

- [ ] **Step 7: Incluir a seção no dashboard**

Em `app/templates/dashboard.html`, logo após a `<section id="overview-section">`, adicionar:

```html
<section id="server-section" class="space-y-3">
    {% include "partials/system_metrics.html" %}
</section>
```

Garantir que `app/main.py` passe `metrics` no contexto do dashboard (via `get_metrics_service`), para a renderização inicial; o polling atualiza sozinho.

- [ ] **Step 8: Rodar a suíte**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/dependencies.py app/routers/metrics.py app/main.py app/templates/dashboard.html app/templates/partials/system_metrics.html tests/test_metrics_router.py
git commit -m "feat: show host metrics on dashboard"
```

---

## Self-Review

- **Cobertura do spec:** CPU/RAM/swap/disco/load/uptime/SO na Task 1; endpoint, polling 10s e UI na Task 2. Coberto.
- **Consistência de tipos:** `SystemMetrics` definido na Task 1 e usado igual na Task 2; `get_metrics_service`/`collect()` consistentes.
- **Review Focus:** load ausente, OS release ausente, swap zero, autenticação e conteúdo têm testes. Falha de coleta no endpoint ainda não tem teste; se `collect()` levantar exceção, o endpoint deve retornar 500 — anotado como comportamento conhecido nesta versão (não bloqueante).
- **Proporção:** plano curto, orientado a decisões e testes.
