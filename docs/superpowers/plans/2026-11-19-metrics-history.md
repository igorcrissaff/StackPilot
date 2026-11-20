# Métricas com histórico, intervalo configurável e exportação CSV — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar intervalo de atualização configurável (5–900s), gráfico recente de consumo e histórico de médias de 5 min em SQLite com exportação CSV.

**Architecture:** Um coletor asyncio no `lifespan` amostra o host continuamente, mantém um buffer recente em memória (gráfico) e grava a média de cada bucket de 5 min no SQLite (peso por `sample_count`). Configuração fica em tabela `app_settings`; UI usa Chart.js via CDN e endpoints HTMX.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, HTMX, Alpine, Tailwind, Chart.js (CDN), sqlite3, psutil, pytest.

**Spec:** `docs/superpowers/specs/2026-11-19-metrics-history-design.md`

## Global Constraints

- Intervalo configurável: inteiro entre 5 e 900 segundos, default 10.
- Janela do gráfico: `multiplier × intervalo`, multiplier ∈ {10,20,…,100} (passo 10), default 30.
- Histórico: média de bucket de 300s, guardado indefinidamente, arquivo SQLite separado do DB do Hub.
- Coleta: a cada `min(10, intervalo)` segundos.
- Todas as rotas novas autenticadas; sem Node.js.
- CSV: todas as linhas quando sem filtro.

## Review Focus

- Intervalo salvo inválido/não numérico não pode quebrar a página de settings nem o dashboard (deve cair no default 10).
- Reinício no meio de um bucket não pode sobrescrever a média já gravada (média ponderada por `sample_count`).
- Gráfico deve ter exatamente `multiplier` pontos, com lacunas (`null`) quando não houver amostra na fatia, sem erro no Chart.js.
- Swap com `swap_total == 0` não deve aparecer no gráfico.
- Exportação com banco vazio/rota sem auth deve responder de forma segura (CSV só com cabeçalho / 303 para login).

---

### Task 1: Repositório de histórico em SQLite

**Files:**
- Modify: `app/config.py`
- Modify: `app/dependencies.py`
- Create: `app/services/metrics_history.py`
- Test: `tests/test_metrics_history.py`

**Interfaces:**
- Produces: `HistoryBucket` (Pydantic) com `bucket_start: int`, `cpu_percent: float`, `memory_percent: float`, `memory_used: int`, `memory_total: int`, `swap_percent: float`, `swap_used: int`, `swap_total: int`, `disk_percent: float`, `disk_used: int`, `disk_total: int`, `load_1/5/15: float | None`, `sample_count: int`.
- Produces: `MetricsHistoryRepository(db_path)` com `upsert_bucket(bucket: HistoryBucket) -> None` e `list_buckets(start: int | None = None, end: int | None = None) -> list[HistoryBucket]`.
- Produces: `_resolve_db_path(configured: Path, fallback_name: str = "stackpilot.db") -> Path` e `get_metrics_history() -> MetricsHistoryRepository`.
- Config field: `metrics_db_path: Path = Path("/opt/stackpilot/metrics.db")`.

- [ ] **Step 1: Escrever testes que falham em `tests/test_metrics_history.py`**

```python
from app.services.metrics_history import HistoryBucket, MetricsHistoryRepository


def _bucket(start, count, cpu):
    return HistoryBucket(
        bucket_start=start, cpu_percent=cpu, memory_percent=50.0,
        memory_used=100, memory_total=200, swap_percent=0.0,
        swap_used=0, swap_total=0, disk_percent=10.0, disk_used=10,
        disk_total=100, load_1=0.5, load_5=0.4, load_15=0.3,
        sample_count=count,
    )


def test_upsert_weighted_merge(tmp_path):
    repo = MetricsHistoryRepository(tmp_path / "m.db")
    repo.upsert_bucket(_bucket(300, 2, 10.0))
    repo.upsert_bucket(_bucket(300, 3, 20.0))
    rows = repo.list_buckets()
    assert len(rows) == 1
    assert rows[0].sample_count == 5
    assert abs(rows[0].cpu_percent - 16.0) < 1e-9


def test_list_ordered_and_filtered(tmp_path):
    repo = MetricsHistoryRepository(tmp_path / "m.db")
    repo.upsert_bucket(_bucket(600, 1, 30.0))
    repo.upsert_bucket(_bucket(300, 1, 10.0))
    assert [r.bucket_start for r in repo.list_buckets()] == [300, 600]
    assert [r.bucket_start for r in repo.list_buckets(start=400)] == [600]
    assert [r.bucket_start for r in repo.list_buckets(start=300, end=600)] == [300]


def test_upsert_preserves_none_loads(tmp_path):
    repo = MetricsHistoryRepository(tmp_path / "m.db")
    b = _bucket(300, 1, 10.0)
    b.load_1 = b.load_5 = b.load_15 = None
    repo.upsert_bucket(b)
    repo.upsert_bucket(b)
    row = repo.list_buckets()[0]
    assert row.load_1 is None and row.load_5 is None and row.load_15 is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_metrics_history.py -q`
Expected: FAIL (`ModuleNotFoundError: app.services.metrics_history`).

- [ ] **Step 3: Implementar**

- `app/config.py`: adicionar `metrics_db_path`.
- `app/dependencies.py`: mudar `_resolve_db_path(configured, fallback_name="stackpilot.db")` e ajustar `get_hub_cache` para `_resolve_db_path(get_settings().hub_db_path)`; adicionar `get_metrics_history()` usando `_resolve_db_path(settings.metrics_db_path, "metrics.db")`.
- `app/services/metrics_history.py`: `_connect()` com `PRAGMA journal_mode=WAL` e `row_factory = sqlite3.Row`, `init_db()` criando `metrics_history` com PK `bucket_start`; `upsert_bucket` lê a linha existente e faz:
  - `novo = (antigo * antigo_count + novo * novo_count) / (antigo_count + novo_count)` para campos numéricos;
  - `sample_count = antigo_count + novo_count`;
  - campos de load: se a linha antiga e a nova forem `None` → `None`; se uma for `None` → usa a outra; senão média ponderada.
  - insere ou atualiza (`ON CONFLICT(bucket_start) DO UPDATE`).
- `list_buckets` com `WHERE bucket_start >= ?` / `<= ?` conforme filtros e `ORDER BY bucket_start ASC`.

- [ ] **Step 4: Rodar e passar**

Run: `pytest tests/test_metrics_history.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/dependencies.py app/services/metrics_history.py tests/test_metrics_history.py
git commit -m "feat: add metrics history repository"
```

---

### Task 2: Configuração persistida do intervalo

**Files:**
- Create: `app/services/metrics_settings.py`
- Modify: `app/dependencies.py`
- Test: `tests/test_metrics_settings.py`

**Interfaces:**
- Produces: `MIN_REFRESH_SECONDS = 5`, `MAX_REFRESH_SECONDS = 900`, `DEFAULT_REFRESH_SECONDS = 10`.
- Produces: `MetricsSettingsStore(db_path)` com `get_refresh_interval() -> int` e `set_refresh_interval(seconds: int) -> None` (levanta `ValueError` para fora de 5–900 ou não inteiro).
- Produces: `get_metrics_settings() -> MetricsSettingsStore`.

- [ ] **Step 1: Testes que falham**

```python
import pytest

from app.services.metrics_settings import (
    DEFAULT_REFRESH_SECONDS, MetricsSettingsStore,
)


def test_default_interval(tmp_path):
    store = MetricsSettingsStore(tmp_path / "m.db")
    assert store.get_refresh_interval() == DEFAULT_REFRESH_SECONDS


def test_persists_interval(tmp_path):
    path = tmp_path / "m.db"
    MetricsSettingsStore(path).set_refresh_interval(5)
    assert MetricsSettingsStore(path).get_refresh_interval() == 5
    MetricsSettingsStore(path).set_refresh_interval(900)
    assert MetricsSettingsStore(path).get_refresh_interval() == 900


@pytest.mark.parametrize("value", [4, 901, 0, -1])
def test_rejects_out_of_range(tmp_path, value):
    store = MetricsSettingsStore(tmp_path / "m.db")
    with pytest.raises(ValueError):
        store.set_refresh_interval(value)


@pytest.mark.parametrize("value", ["abc", 10.5, None])
def test_rejects_non_integer(tmp_path, value):
    store = MetricsSettingsStore(tmp_path / "m.db")
    with pytest.raises(ValueError):
        store.set_refresh_interval(value)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_metrics_settings.py -q`
Expected: FAIL (módulo ausente).

- [ ] **Step 3: Implementar**

`MetricsSettingsStore`: `init_db()` cria `app_settings(key TEXT PRIMARY KEY, value TEXT)`; `get_refresh_interval` lê a chave `metrics_refresh_interval_seconds`, converte para int e retorna default 10 se ausente/inválida; `set_refresh_interval` valida `isinstance(seconds, int) and not isinstance(seconds, bool)` e `5 <= seconds <= 900`, senão `ValueError`, e faz UPSERT. Adicionar `get_metrics_settings()` em `app/dependencies.py` usando o mesmo `metrics_db_path`.

- [ ] **Step 4: Rodar e passar**

Run: `pytest tests/test_metrics_settings.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/metrics_settings.py app/dependencies.py tests/test_metrics_settings.py
git commit -m "feat: persist metrics refresh interval"
```

---

### Task 3: Coletor com buffer recente e médias de 5 min

**Files:**
- Create: `app/services/metrics_collector.py`
- Test: `tests/test_metrics_collector.py`

**Interfaces:**
- Consumes: `MetricsService.collect() -> SystemMetrics`; `MetricsHistoryRepository.upsert_bucket`; `MetricsSettingsStore.get_refresh_interval()`.
- Produces: `RecentSample` (dataclass) com `timestamp: float`, `cpu_percent: float`, `memory_percent: float`, `swap_percent: float`, `disk_percent: float`.
- Produces: `MetricsCollector(metrics_service, history, settings, sample_interval=10)` com:
  - `record(metrics: SystemMetrics, now: float | None = None) -> None`
  - `chart_series(multiplier: int, interval: int, now: float | None = None) -> dict` → `{"labels": list[int], "cpu": list[float|None], "memory": [...], "swap": [...], "disk": [...]}` (epoch em segundos)
  - `flush() -> None`
  - `start() -> None`, `stop() -> None`
- Produces: `get_metrics_collector(request: Request) -> MetricsCollector` em `app/dependencies.py` (usa `request.app.state.metrics_collector`, criando um não-iniciado se ausente).

- [ ] **Step 1: Testes que falham**

```python
import time

from app.services.metrics_collector import MetricsCollector
from app.services.metrics_service import SystemMetrics
from app.services.metrics_settings import MetricsSettingsStore
from app.services.metrics_history import HistoryBucket, MetricsHistoryRepository

GB = 1024 ** 3


class FakeMetrics:
    def __init__(self):
        self.cpu = 0.0

    def collect(self):
        return SystemMetrics(
            cpu_percent=self.cpu, cpu_count=4, load_1=1.0, load_5=1.0, load_15=1.0,
            memory_used=GB, memory_total=4 * GB, memory_percent=25.0,
            swap_used=0, swap_total=0, swap_percent=0.0,
            disk_used=GB, disk_total=10 * GB, disk_percent=10.0,
            uptime_seconds=100, os_name="Linux", os_version="1",
            kernel="k", architecture="x86_64", hostname="h",
        )


class FakeHistory:
    def __init__(self):
        self.rows = []

    def upsert_bucket(self, bucket):
        self.rows.append(bucket)


class FakeSettings:
    def __init__(self, interval=10):
        self.interval = interval

    def get_refresh_interval(self):
        return self.interval


def _collector(interval=10):
    return MetricsCollector(FakeMetrics(), FakeHistory(), FakeSettings(interval))


def test_flush_on_bucket_change_averages_samples():
    c = _collector()
    svc = FakeMetrics()
    for cpu, t in [(10.0, 0.0), (20.0, 10.0), (30.0, 300.0)]:
        svc.cpu = cpu
        c.record(svc.collect(), now=1000.0 + t)
    # 1000..1010 no bucket 900; 1300 no bucket 1200 -> flush do anterior
    assert len(c.history.rows) == 1
    assert c.history.rows[0].bucket_start == 900
    assert c.history.rows[0].sample_count == 2
    assert abs(c.history.rows[0].cpu_percent - 15.0) < 1e-9


def test_buffer_prunes_to_100_intervals():
    c = _collector(interval=5)
    svc = FakeMetrics()
    base = 1000.0
    for i in range(300):
        c.record(svc.collect(), now=base + i)
    oldest = min(s.timestamp for s in c._buffer)
    assert oldest >= (base + 299) - 100 * 5


def test_chart_series_has_multiplier_points():
    c = _collector(interval=10)
    svc = FakeMetrics()
    now = 10_000.0
    for i in range(40):
        svc.cpu = float(i)
        c.record(svc.collect(), now=now - i * 10)
    data = c.chart_series(10, 10, now=now)
    assert len(data["labels"]) == 10
    assert len(data["cpu"]) == 10
    assert data["swap"] == [0.0] * 10
    assert data["cpu"][-1] is not None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_metrics_collector.py -q`
Expected: FAIL (módulo ausente).

- [ ] **Step 3: Implementar**

- `record`: usa `now or time.time()`; `bucket_start = int(now) - int(now) % 300`; se o bucket mudou e havia acumulador, chama `flush()`; adiciona `RecentSample` ao `deque`; acumula o `SystemMetrics`; pode o buffer para `timestamp >= now - 100 * settings.get_refresh_interval()`.
- `flush`: se vazio retorna; monta `HistoryBucket` com médias dos acumulados (load: `None` se todos `None`), `sample_count=len`, `history.upsert_bucket(...)`, limpa acumulador.
- `chart_series`: `window = multiplier * interval`; `now = now or time.time()`; `cutoff = now - window`; `labels`/séries com `multiplier` posições; para cada amostra com `timestamp >= cutoff`, `idx = int((s.timestamp - cutoff) // interval)` clampado em `0..multiplier-1`, acumular por fatia; média por fatia; sem amostra → `None`. `swap` usa `None` por fatia vazia.
- `start`: cria `asyncio.Task(self._run())`; `_run` lê `interval` das settings, `sleep = min(sample_interval, interval)`, `metrics = await asyncio.to_thread(self.metrics.collect)`, `self.record(metrics)`, dorme, repetindo; `stop` cancela o task, aguarda e faz `flush()`.
- `app/dependencies.py`: `get_metrics_collector(request)` como descrito.

- [ ] **Step 4: Rodar e passar**

Run: `pytest tests/test_metrics_collector.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/metrics_collector.py app/dependencies.py tests/test_metrics_collector.py
git commit -m "feat: add metrics collector with recent buffer"
```

---

### Task 4: Lifespan, chart no `/metrics` e partial dinâmica

**Files:**
- Modify: `app/main.py`
- Modify: `app/routers/metrics.py`
- Modify: `app/templates/partials/system_metrics.html`
- Modify: `app/templates/dashboard.html`
- Create: `tests/conftest.py`
- Test: `tests/test_metrics_router.py`

**Interfaces:**
- Consumes: `get_metrics_collector`, `get_metrics_settings`, `get_metrics_service`.
- Produces: `GET /metrics?multiplier=N` (N inteiro, 10–100, múltiplo de 10; inválido → 400). Renderiza a partial com `metrics`, `chart`, `interval`, `multiplier`, `multipliers=range(10,101,10)`.

- [ ] **Step 1: `tests/conftest.py` isolando o banco**

```python
import os
import tempfile

os.environ.setdefault("METRICS_DB_PATH", os.path.join(tempfile.mkdtemp(), "metrics.db"))
```

- [ ] **Step 2: Atualizar testes que falham em `tests/test_metrics_router.py`**

Adicionar:

```python
def test_metrics_rejects_invalid_multiplier():
    app.dependency_overrides[get_metrics_collector] = lambda: MagicMock()
    try:
        assert _client().get("/metrics?multiplier=15").status_code == 400
        assert _client().get("/metrics?multiplier=0").status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_metrics_includes_chart_payload():
    mock = MagicMock()
    mock.collect.return_value = _metrics()
    collector = MagicMock()
    collector.chart_series.return_value = {
        "labels": [1, 2], "cpu": [1.0, 2.0], "memory": [3.0, 4.0],
        "swap": [0.0, 0.0], "disk": [5.0, 6.0],
    }
    settings = MagicMock()
    settings.get_refresh_interval.return_value = 10
    app.dependency_overrides[get_metrics_service] = lambda: mock
    app.dependency_overrides[get_metrics_collector] = lambda: collector
    app.dependency_overrides[get_metrics_settings] = lambda: settings
    try:
        r = _client().get("/metrics?multiplier=10")
        assert r.status_code == 200
        assert 'id="metrics-chart-data"' in r.text
        assert 'id="metrics-window"' in r.text
        assert "every 10s" in r.text
        assert 'value="10" selected' in r.text
    finally:
        app.dependency_overrides.clear()
```

Importar `get_metrics_collector` e `get_metrics_settings` de `app.dependencies`.

- [ ] **Step 3: Rodar e ver falhar**

Run: `pytest tests/test_metrics_router.py -q`
Expected: FAIL (rotas/template ainda sem chart e sem validação).

- [ ] **Step 4: Implementar**

- `app/main.py`: `from contextlib import asynccontextmanager`; criar `lifespan(app)` que monta `MetricsCollector(get_metrics_service(), get_metrics_history(), get_metrics_settings())`, guarda em `app.state.metrics_collector`, chama `start()`, e no `finally` chama `stop()`; `app = FastAPI(title="StackPilot", lifespan=lifespan)`.
- Dashboard: passar `chart=collector.chart_series(30, interval)` usando o coletor e as settings; manter `scroll`.
- `/metrics`: ler `multiplier` (default 30), validar `10 <= n <= 100 and n % 10 == 0` senão `HTTPException(400)`; `interval = metrics_settings.get_refresh_interval()`; `chart = collector.chart_series(multiplier, interval)`; renderizar partial com todos os valores.
- Partial: raiz `hx-get="/metrics"`, `hx-trigger="every {{ interval }}s"`, `hx-include="#metrics-window"`, `hx-swap="outerHTML"`. Adicionar no cabeçalho um `<select id="metrics-window" name="multiplier" hx-get="/metrics" hx-include="this" hx-target="#system-metrics" hx-swap="outerHTML">` com `{% for n in multipliers %}<option value="{{ n }}" {% if n == multiplier %}selected{% endif %}>` rotulando `n*interval` s; um `<canvas id="metrics-chart">`; um `<script type="application/json" id="metrics-chart-data">{{ chart|tojson }}</script>`; um link "Exportar CSV" para `/metrics/export.csv`; texto "atualiza a cada {{ interval }}s".
- Manter os cards existentes. Se `metrics` ausente, mostrar erro como hoje.

- [ ] **Step 5: Rodar e passar**

Run: `pytest tests/test_metrics_router.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/routers/metrics.py app/templates/partials/system_metrics.html app/templates/dashboard.html tests/conftest.py tests/test_metrics_router.py
git commit -m "feat: add metrics chart and dynamic interval"
```

---

### Task 5: Página de configurações com o intervalo

**Files:**
- Create: `app/routers/settings.py`
- Create: `app/templates/settings.html`
- Create: `app/templates/partials/metrics_settings.html`
- Modify: `app/main.py` (incluir router)
- Modify: `app/templates/dashboard.html` (links de navegação)
- Test: `tests/test_settings_router.py`

**Interfaces:**
- Consumes: `get_metrics_settings`, `require_auth`.
- Produces: `GET /settings` (HTML com o formulário), `POST /settings/metrics` (form `interval: str`; válido salva e retorna 200 com partial de sucesso; inválido 200 com partial de erro; sem `HX-Request` redireciona 303 para `/settings`).

- [ ] **Step 1: Testes que falham**

```python
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.dependencies import get_metrics_settings
from app.main import app


def _client():
    c = TestClient(app)
    c.post("/login", data={"username": "admin", "password": "admin"})
    return c


def test_settings_requires_auth():
    r = TestClient(app).get("/settings", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_settings_page_shows_interval():
    store = MagicMock()
    store.get_refresh_interval.return_value = 42
    app.dependency_overrides[get_metrics_settings] = lambda: store
    try:
        r = _client().get("/settings")
        assert r.status_code == 200
        assert 'name="interval"' in r.text
        assert 'value="42"' in r.text
    finally:
        app.dependency_overrides.clear()


def test_post_saves_interval():
    store = MagicMock()
    app.dependency_overrides[get_metrics_settings] = lambda: store
    try:
        r = _client().post(
            "/settings/metrics", data={"interval": "30"}, headers={"HX-Request": "true"}
        )
        assert r.status_code == 200
        store.set_refresh_interval.assert_called_once_with(30)
        assert "salvo" in r.text.lower()
    finally:
        app.dependency_overrides.clear()


def test_post_rejects_invalid_interval():
    store = MagicMock()
    store.set_refresh_interval.side_effect = ValueError("faixa")
    app.dependency_overrides[get_metrics_settings] = lambda: store
    try:
        r = _client().post(
            "/settings/metrics", data={"interval": "2"}, headers={"HX-Request": "true"}
        )
        assert r.status_code == 200
        assert "5" in r.text and "900" in r.text
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_settings_router.py -q`
Expected: FAIL (rota ausente).

- [ ] **Step 3: Implementar**

- `app/routers/settings.py`: `GET /settings` renderiza `settings.html` com `interval` e sem mensagem; `POST /settings/metrics` faz `int(form["interval"])` (erro → mensagem de validação), chama `set_refresh_interval` (captura `ValueError`), e:
  - com header `HX-Request`: `TemplateResponse` de `partials/metrics_settings.html` com `interval`, `message`/`error`;
  - sem: `RedirectResponse("/settings", status_code=303)`.
- `settings.html`: `{% extends "base.html" %}`; barra com link "Voltar" para `/`; card "Métricas" incluindo `partials/metrics_settings.html`.
- `partials/metrics_settings.html`: form `hx-post="/settings/metrics" hx-target="#metrics-settings" hx-swap="outerHTML"` com input number `name="interval" min="5" max="900" step="1" value="{{ interval }}"`, botão Salvar e link "Exportar CSV" para `/metrics/export.csv`; mensagem de sucesso/erro quando houver.
- `app/main.py`: incluir `settings.router`.
- `dashboard.html`: adicionar link "Configurações" (ícone engrenagem) no grupo de navegação lateral e no drawer mobile.

- [ ] **Step 4: Rodar e passar**

Run: `pytest tests/test_settings_router.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/routers/settings.py app/templates/settings.html app/templates/partials/metrics_settings.html app/main.py app/templates/dashboard.html tests/test_settings_router.py
git commit -m "feat: add metrics settings page"
```

---

### Task 6: Exportação CSV do histórico

**Files:**
- Modify: `app/routers/metrics.py`
- Test: `tests/test_metrics_router.py`

**Interfaces:**
- Consumes: `get_metrics_history()`; `MetricsHistoryRepository.list_buckets(start, end)`.
- Produces: `GET /metrics/export.csv?start=&end=` (auth) → CSV com cabeçalho e `Content-Disposition: attachment; filename=stackpilot-metrics-YYYYMMDD.csv`.

- [ ] **Step 1: Testes que falham (adicionar em `tests/test_metrics_router.py`)**

```python
from app.services.metrics_history import HistoryBucket


def test_export_requires_auth():
    r = TestClient(app).get("/metrics/export.csv", follow_redirects=False)
    assert r.status_code == 303


def test_export_streams_csv():
    repo = MagicMock()
    repo.list_buckets.return_value = [
        HistoryBucket(
            bucket_start=300, cpu_percent=10.0, memory_percent=50.0,
            memory_used=1, memory_total=2, swap_percent=0.0, swap_used=0,
            swap_total=0, disk_percent=10.0, disk_used=1, disk_total=10,
            load_1=0.1, load_5=0.2, load_15=0.3, sample_count=30,
        )
    ]
    app.dependency_overrides[get_metrics_history] = lambda: repo
    try:
        r = _client().get("/metrics/export.csv?start=100&end=400")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]
        lines = r.text.strip().splitlines()
        assert lines[0].startswith("bucket_start,")
        assert "1970-01-01T00:05:00" in lines[1]
        repo.list_buckets.assert_called_once_with(100, 400)
    finally:
        app.dependency_overrides.clear()
```

Importar `get_metrics_history` de `app.dependencies`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_metrics_router.py -q`
Expected: FAIL (rota ausente).

- [ ] **Step 3: Implementar**

Rota `@router.get("/metrics/export.csv")` com `Depends(require_auth)` e `history=Depends(get_metrics_history)`; parses opcionais `start`/`end` como int (ausente → `None`); monta linhas via `csv.writer` num `io.StringIO` por linha, usando `datetime.fromtimestamp(bucket_start, tz=timezone.utc).isoformat()`; `StreamingResponse(iter([...]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="stackpilot-metrics-{date}.csv"'})`.

- [ ] **Step 4: Rodar e passar**

Run: `pytest tests/test_metrics_router.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/routers/metrics.py tests/test_metrics_router.py
git commit -m "feat: export metrics history as CSV"
```

---

### Task 7: Gráfico no navegador (Chart.js) e integração final

**Files:**
- Create: `app/static/js/metrics_chart.js`
- Modify: `app/templates/dashboard.html` (carregar Chart.js e o JS)
- Test: `tests/test_routers.py` (novo teste de asset) e suíte completa

**Interfaces:**
- Consumes: `#metrics-chart`, `#metrics-chart-data` (JSON), `#metrics-window`.
- Produces: `GET /static/js/metrics_chart.js` acessível.

- [ ] **Step 1: Teste que falha**

Adicionar em `tests/test_routers.py`:

```python
def test_metrics_chart_asset_served():
    r = TestClient(app).get("/static/js/metrics_chart.js")
    assert r.status_code == 200
    assert "Chart" in r.text
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_routers.py::test_metrics_chart_asset_served -q`
Expected: FAIL (404).

- [ ] **Step 3: Implementar**

- `metrics_chart.js`: função `renderMetricsChart()` que lê o JSON de `#metrics-chart-data`, obtém `<canvas id="metrics-chart">` e cria/atualiza `window.metricsChart` com `type: "line"`, `parsing: false`, `scales.y` de 0 a 100, `spanGaps: false`, dataseries CPU/memória/disco/swap; executa em `DOMContentLoaded` e em `document.body.addEventListener("htmx:afterSwap", renderMetricsChart)` (e `htmx:afterSettle`), protegendo contra canvas ausente/JSON inválido.
- `dashboard.html`: adicionar no bloco de scripts `{% block scripts %}` (criar se não existir em `base.html`) `<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>` e `<script src="/static/js/metrics_chart.js"></script>`. Se `base.html` não tiver `{% block scripts %}`, adicioná-lo antes de `</body>` e usá-lo.

- [ ] **Step 4: Rodar o asset e a suíte**

Run: `pytest tests/test_routers.py::test_metrics_chart_asset_served -q` → PASS
Run: `pytest -q` → PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add app/static/js/metrics_chart.js app/templates/base.html app/templates/dashboard.html tests/test_routers.py
git commit -m "feat: render metrics history chart"
```

---

## Self-Review

- **Cobertura:** intervalo configurável (Tasks 2, 4, 5); gráfico recente (Tasks 3, 4, 7); médias de 5 min em SQLite (Tasks 1, 3); export CSV (Task 6); coleta contínua (Tasks 3, 4). Coberto.
- **Consistência:** `HistoryBucket`/`list_buckets` iguais nas Tasks 1/6; `chart_series` iguais nas Tasks 3/4; `get_metrics_*` definidos nas Tasks 1/2/3 e usados nas 4/5/6.
- **Review Focus:** intervalo inválido (Task 5 testa), reinício/média ponderada (Task 1 testa), `multiplier` exato/lacunas (Task 3 testa), swap fora do gráfico (Task 3 usa `0.0`; ocultar no JS da Task 7 conforme spec), CSV vazio/auth (Task 6 testa auth; vazio retorna só cabeçalho pela implementação).
- **Proporção:** 7 tasks pequenas, cada uma com teste e commit próprios.
