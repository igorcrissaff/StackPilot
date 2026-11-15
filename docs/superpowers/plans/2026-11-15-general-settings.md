# Configurações Gerais (hostname base) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar uma área de Configurações Gerais que permite alterar o hostname base pelo painel, persistindo em SQLite e aplicando imediatamente às rotas Traefik, com estrutura extensível para idioma e tema no futuro.

**Architecture:** Uma tabela `app_settings(scope, key, value)` no mesmo SQLite do cache guarda overrides; `SettingsService` lê o override e cai no valor do `.env`. As dependências FastAPI expõem o hostname efetivo, usado pelo `TraefikService`, rotas e dashboard. Ao salvar um novo hostname, as regras `Host(...)` do arquivo `stackpilot-routes.yml` são regravadas. Uma página `/settings` com HTMX salva/restaura o valor.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, HTMX, Tailwind via CDN, `sqlite3` (stdlib), pytest.

**Spec:** `docs/superpowers/specs/2026-11-15-general-settings-design.md`

## Global Constraints

- Python 3.11+; nenhuma dependência nova (usar `sqlite3` da stdlib).
- Manter o stack atual: FastAPI + Jinja2 + HTMX + Tailwind via CDN, sem build step.
- Templates e mensagens de UI em português (pt-BR), seguindo o visual existente (cores `#0c1017`, `#111722`, `#161e2e`, `#232f45`).
- Todas as rotas novas exigem `Depends(require_auth)`.
- Valor efetivo do hostname: override do banco, senão `BASE_DOMAIN` do `.env`; mudanças valem sem restart.
- Não escrever no `.env`; não remover o suporte a `BASE_DOMAIN`.
- Nenhum campo de idioma/tema nesta versão; apenas a estrutura preparada.
- Rodar testes com o venv do projeto: `.venv\Scripts\python.exe -m pytest`.

## Review Focus

- Hostname com espaços, maiúsculas, ponto final ou esquema deve ser normalizado ou rejeitado, nunca gravado cru (Task 1/2).
- Salvar o mesmo hostname atual deve ser idempotente e não reescrever/limpar rotas (Task 4/5).
- Falha ao reescrever o YAML ao trocar o hostname não pode deixar configuração e rotas divergentes (Task 5).
- Routers fora do domínio antigo no mesmo arquivo devem permanecer intactos (Task 4).
- Leitura do banco falhando não pode derrubar o painel; deve cair no valor do `.env` (Task 3).

---

### Task 1: Normalizador de hostname compartilhado

**Files:**
- Modify: `app/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nada.
- Produces: `normalize_base_domain(value: str) -> str` em `app/config.py`; normaliza (trim, lowercase, remove ponto final) e levanta `ValueError` para valor inválido (vazio, com `://`, `/` ou espaço). `Settings.base_domain` continua com o mesmo comportamento.

- [ ] **Step 1: Escrever o teste que falha**

Adicionar em `tests/test_config.py`:

```python
def test_normalize_base_domain_trims_lowercases_and_strips_dot():
    from app.config import normalize_base_domain

    assert normalize_base_domain(" Lab.Local. ") == "lab.local"


def test_normalize_base_domain_rejects_scheme_and_path():
    from app.config import normalize_base_domain
    import pytest

    with pytest.raises(ValueError):
        normalize_base_domain("http://lab.local")
    with pytest.raises(ValueError):
        normalize_base_domain("lab.local/painel")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py::test_normalize_base_domain_trims_lowercases_and_strips_dot -v`
Expected: FAIL com `ImportError`/`cannot import name 'normalize_base_domain'`.

- [ ] **Step 3: Implementar `normalize_base_domain(value: str) -> str` em `app/config.py`**

Mover o corpo do validator atual para a função de módulo (antes da classe) e fazer `Settings.validate_base_domain` chamar `normalize_base_domain`. A função levanta `ValueError("BASE_DOMAIN must be a bare domain, e.g. home.arpa")` para inválidos.

- [ ] **Step 4: Rodar testes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: PASS (todos, incluindo os de `Settings`).

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "refactor: extract shared base domain normalizer"
```

---

### Task 2: SettingsService com persistência em SQLite

**Files:**
- Create: `app/services/settings_service.py`
- Test: `tests/test_settings_service.py`

**Interfaces:**
- Consumes: `normalize_base_domain` (Task 1).
- Produces:
  - `GLOBAL_SCOPE = "global"`, `BASE_DOMAIN_KEY = "base_domain"`.
  - `class SettingsService:` com `__init__(self, db_path: Path | str)`, `init_db(self) -> None`, `get(self, scope: str, key: str) -> str | None`, `set(self, scope: str, key: str, value: str) -> None`, `delete(self, scope: str, key: str) -> None`, `all(self, scope: str) -> dict[str, str]`, `get_base_domain(self, default: str) -> str`, `set_base_domain(self, value: str) -> str`, `reset_base_domain(self) -> None`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_settings_service.py`:

```python
import pytest

from app.services.settings_service import (
    BASE_DOMAIN_KEY,
    GLOBAL_SCOPE,
    SettingsService,
)


def _svc(tmp_path):
    return SettingsService(tmp_path / "settings.db")


def test_set_get_roundtrip(tmp_path):
    svc = _svc(tmp_path)
    svc.set(GLOBAL_SCOPE, "x", "1")
    assert svc.get(GLOBAL_SCOPE, "x") == "1"
    assert svc.get(GLOBAL_SCOPE, "missing") is None


def test_all_and_delete(tmp_path):
    svc = _svc(tmp_path)
    svc.set(GLOBAL_SCOPE, "a", "1")
    svc.set(GLOBAL_SCOPE, "b", "2")
    assert svc.all(GLOBAL_SCOPE) == {"a": "1", "b": "2"}
    svc.delete(GLOBAL_SCOPE, "a")
    assert svc.all(GLOBAL_SCOPE) == {"b": "2"}


def test_get_base_domain_falls_back_to_default(tmp_path):
    svc = _svc(tmp_path)
    assert svc.get_base_domain("home.arpa") == "home.arpa"


def test_set_base_domain_normalizes_and_overrides(tmp_path):
    svc = _svc(tmp_path)
    assert svc.set_base_domain(" Lab.Local. ") == "lab.local"
    assert svc.get_base_domain("home.arpa") == "lab.local"
    assert svc.get(GLOBAL_SCOPE, BASE_DOMAIN_KEY) == "lab.local"


def test_set_base_domain_rejects_invalid(tmp_path):
    svc = _svc(tmp_path)
    with pytest.raises(ValueError):
        svc.set_base_domain("http://lab.local")
    assert svc.get(GLOBAL_SCOPE, BASE_DOMAIN_KEY) is None


def test_reset_base_domain_reverts_to_default(tmp_path):
    svc = _svc(tmp_path)
    svc.set_base_domain("lab.local")
    svc.reset_base_domain()
    assert svc.get_base_domain("home.arpa") == "home.arpa"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings_service.py -v`
Expected: FAIL com `ModuleNotFoundError: app.services.settings_service`.

- [ ] **Step 3: Implementar `app/services/settings_service.py`**

Usar `sqlite3` com `_connect()` que cria `self.db_path.parent` e aplica `PRAGMA journal_mode=WAL`, e `init_db()` com:

```sql
CREATE TABLE IF NOT EXISTS app_settings (
    scope TEXT NOT NULL,
    key   TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (scope, key)
);
```

`set` usa `INSERT ... ON CONFLICT(scope, key) DO UPDATE SET value=excluded.value`; `get_base_domain` retorna `self.get(GLOBAL_SCOPE, BASE_DOMAIN_KEY) or default`; `set_base_domain` chama `normalize_base_domain`, grava e retorna o valor normalizado; `reset_base_domain` apaga a chave.

- [ ] **Step 4: Rodar testes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/settings_service.py tests/test_settings_service.py
git commit -m "feat: add SQLite-backed settings service"
```

---

### Task 3: Hostname efetivo nas dependências

**Files:**
- Modify: `app/dependencies.py`
- Test: `tests/test_dependencies.py` (criar)

**Interfaces:**
- Consumes: `SettingsService` (Task 2).
- Produces:
  - `get_settings_service() -> SettingsService` (mesmo caminho de banco do cache).
  - `get_effective_base_domain(settings_svc: SettingsService = Depends(get_settings_service)) -> str` — override do banco, senão `get_settings().base_domain`; em qualquer exceção de leitura, retorna o valor do `.env`.
  - `get_traefik_service(base_domain: str = Depends(get_effective_base_domain)) -> TraefikService` usando o hostname efetivo.
  - Renomear `_resolve_hub_db_path` para `_resolve_db_path` (usado por `get_hub_cache` e `get_settings_service`).

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_dependencies.py`:

```python
from app.config import Settings
from app.services.settings_service import SettingsService
from app.dependencies import get_effective_base_domain, get_settings_service, get_traefik_service


class _BrokenService:
    def get_base_domain(self, default):
        raise RuntimeError("db unavailable")


def test_effective_base_domain_uses_override(tmp_path, monkeypatch):
    svc = SettingsService(tmp_path / "s.db")
    svc.set_base_domain("lab.local")
    monkeypatch.setattr("app.dependencies.get_settings", lambda: Settings(_env_file=None, base_domain="home.arpa"))
    assert get_effective_base_domain(svc) == "lab.local"


def test_effective_base_domain_falls_back_to_env(tmp_path, monkeypatch):
    svc = SettingsService(tmp_path / "s.db")
    monkeypatch.setattr("app.dependencies.get_settings", lambda: Settings(_env_file=None, base_domain="home.arpa"))
    assert get_effective_base_domain(svc) == "home.arpa"


def test_effective_base_domain_falls_back_when_db_fails(monkeypatch):
    monkeypatch.setattr("app.dependencies.get_settings", lambda: Settings(_env_file=None, base_domain="home.arpa"))
    assert get_effective_base_domain(_BrokenService()) == "home.arpa"


def test_traefik_service_uses_effective_base_domain(tmp_path):
    svc = get_traefik_service(base_domain="lab.local")
    assert svc.base_domain == "lab.local"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python.exe -m pytest tests/test_dependencies.py -v`
Expected: FAIL com `ImportError` de `get_effective_base_domain` / `_BrokenService`.

- [ ] **Step 3: Implementar em `app/dependencies.py`**

Adicionar import de `Depends` e `SettingsService`, `get_settings_service` usando `_resolve_db_path(get_settings().hub_db_path)`, e `get_effective_base_domain` com `try/except Exception` retornando `get_settings().base_domain`. Trocar a assinatura de `get_traefik_service` para receber `base_domain: str = Depends(get_effective_base_domain)` e passar isso ao `TraefikService`.

- [ ] **Step 4: Rodar testes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_dependencies.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/dependencies.py tests/test_dependencies.py
git commit -m "feat: resolve effective base domain from settings store"
```

---

### Task 4: Migração de rotas ao trocar o hostname

**Files:**
- Modify: `app/services/traefik_service.py`
- Test: `tests/test_traefik_service.py`

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces: `TraefikService.rewrite_base_domain(self, old: str, new: str) -> int` — normaliza `old`/`new` (trim, lowercase, sem ponto final); para cada router cuja `rule` seja `Host(`<sub>.<old>`)` com subdomínio válido, regrava para `Host(`<sub>.<new>`)`; retorna a quantidade reescrita; grava o arquivo apenas se `count > 0`; se `old == new` retorna `0`; routers fora do domínio antigo ficam intocados.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar em `tests/test_traefik_service.py`:

```python
def test_rewrite_base_domain_moves_managed_routers(tmp_path):
    svc = TraefikService(dynamic_dir=tmp_path, base_domain="home.arpa")
    svc.upsert_route(RouteConfig(name="app1", subdomain="app1", target_url="http://app1:80"))

    assert svc.rewrite_base_domain("home.arpa", "lab.local") == 1

    data = yaml.safe_load((tmp_path / "stackpilot-routes.yml").read_text(encoding="utf-8"))
    assert data["http"]["routers"]["app1"]["rule"] == "Host(`app1.lab.local`)"
    assert data["http"]["services"]["app1"]["loadBalancer"]["servers"][0]["url"] == "http://app1:80"


def test_rewrite_base_domain_preserves_other_domains(tmp_path):
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

    assert svc.rewrite_base_domain("home.arpa", "lab.local") == 1

    data = yaml.safe_load((tmp_path / "stackpilot-routes.yml").read_text(encoding="utf-8"))
    assert data["http"]["routers"]["keep"]["rule"] == "Host(`keep.lab.local`)"
    assert data["http"]["routers"]["other"]["rule"] == "Host(`other.example`)"


def test_rewrite_base_domain_same_domain_is_noop(tmp_path):
    svc = TraefikService(dynamic_dir=tmp_path, base_domain="home.arpa")
    svc.upsert_route(RouteConfig(name="app1", subdomain="app1", target_url="http://app1:80"))
    assert svc.rewrite_base_domain("home.arpa", "home.arpa") == 0
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python.exe -m pytest tests/test_traefik_service.py -k rewrite_base_domain -v`
Expected: FAIL com `AttributeError: 'TraefikService' object has no attribute 'rewrite_base_domain'`.

- [ ] **Step 3: Implementar `rewrite_base_domain` em `app/services/traefik_service.py`**

Reaproveitar o parsing de `list_routes` (`rule.removeprefix("Host(`").removesuffix("`)")` + sufixo `".<old>"` + `SUBDOMAIN_RE`). Contar reescritas e chamar `_save_raw` somente quando `count > 0`.

- [ ] **Step 4: Rodar testes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_traefik_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/traefik_service.py tests/test_traefik_service.py
git commit -m "feat: migrate managed route host rules on base domain change"
```

---

### Task 5: Página de configurações, integração e navegação

**Files:**
- Create: `app/routers/settings.py`
- Create: `app/templates/settings.html`
- Create: `app/templates/partials/settings_general_form.html`
- Modify: `app/main.py` (incluir router; dashboard usando hostname efetivo)
- Modify: `app/routers/routes.py` (usar hostname efetivo)
- Modify: `app/templates/dashboard.html` (link Configurações na sidebar e drawer)
- Modify: `app/templates/docker.html` (link Configurações no topo)
- Test: `tests/test_settings_router.py` (criar)
- Modify: `tests/test_routers.py` (nova asserção de hostname efetivo / link)

**Interfaces:**
- Consumes: `SettingsService`, `GLOBAL_SCOPE`, `BASE_DOMAIN_KEY` (Task 2); `get_settings_service`, `get_effective_base_domain`, `get_traefik_service` (Task 3); `rewrite_base_domain` (Task 4).
- Produces rotas:
  - `GET /settings` → `settings.html` com contexto `base_domain`, `default_base_domain`, `is_custom`, `error`, `message`.
  - `POST /settings` (form `base_domain`) → partial `partials/settings_general_form.html`; sucesso `message="Configurações salvas"`; inválido `error="Hostname inválido. Use um domínio simples, ex.: home.arpa"`; falha na migração reverte e retorna `error`.
  - `POST /settings/reset` → remove override, migra de volta ao padrão e retorna o partial com `message="Padrão do ambiente restaurado"`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_settings_router.py`:

```python
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import get_settings_service, get_traefik_service
from app.main import app


def _authed_client():
    client = TestClient(app)
    client.post("/login", data={"username": "admin", "password": "admin"})
    return client


def _override(monkeypatch, settings_svc, traefik_svc, base_domain="home.arpa"):
    monkeypatch.setattr(
        "app.routers.settings.get_settings",
        lambda: Settings(_env_file=None, base_domain=base_domain),
    )
    app.dependency_overrides[get_settings_service] = lambda: settings_svc
    app.dependency_overrides[get_traefik_service] = lambda: traefik_svc


def test_settings_requires_auth():
    resp = TestClient(app).get("/settings", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_settings_page_renders_current_value(monkeypatch):
    settings_svc = MagicMock()
    settings_svc.get_base_domain.return_value = "home.arpa"
    settings_svc.get.return_value = None
    traefik_svc = MagicMock()
    _override(monkeypatch, settings_svc, traefik_svc)
    try:
        resp = _authed_client().get("/settings")
        assert resp.status_code == 200
        assert 'name="base_domain"' in resp.text
        assert 'value="home.arpa"' in resp.text
        assert "Restaurar padrão" in resp.text
    finally:
        app.dependency_overrides.clear()


def test_post_settings_persists_and_migrates(monkeypatch):
    settings_svc = MagicMock()
    settings_svc.get_base_domain.return_value = "home.arpa"
    settings_svc.get.return_value = None
    settings_svc.set_base_domain.return_value = "lab.local"
    traefik_svc = MagicMock()
    _override(monkeypatch, settings_svc, traefik_svc)
    try:
        resp = _authed_client().post("/settings", data={"base_domain": " Lab.Local. "})
        assert resp.status_code == 200
        assert "Configurações salvas" in resp.text
        settings_svc.set_base_domain.assert_called_once_with(" Lab.Local. ")
        traefik_svc.rewrite_base_domain.assert_called_once_with("home.arpa", "lab.local")
    finally:
        app.dependency_overrides.clear()


def test_post_settings_invalid_shows_error(monkeypatch):
    settings_svc = MagicMock()
    settings_svc.get_base_domain.return_value = "home.arpa"
    settings_svc.get.return_value = None
    settings_svc.set_base_domain.side_effect = ValueError("bad")
    traefik_svc = MagicMock()
    _override(monkeypatch, settings_svc, traefik_svc)
    try:
        resp = _authed_client().post("/settings", data={"base_domain": "http://bad"})
        assert resp.status_code == 200
        assert "Hostname inválido" in resp.text
        traefik_svc.rewrite_base_domain.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_post_settings_migration_failure_reverts(monkeypatch):
    settings_svc = MagicMock()
    settings_svc.get_base_domain.return_value = "home.arpa"
    settings_svc.get.return_value = None
    settings_svc.set_base_domain.return_value = "lab.local"
    traefik_svc = MagicMock()
    traefik_svc.rewrite_base_domain.side_effect = OSError("disk full")
    _override(monkeypatch, settings_svc, traefik_svc)
    try:
        resp = _authed_client().post("/settings", data={"base_domain": "lab.local"})
        assert resp.status_code == 200
        assert "não foi possível atualizar as rotas" in resp.text.lower()
        settings_svc.reset_base_domain.assert_called_once()
    finally:
        app.dependency_overrides.clear()


def test_reset_settings_restores_default(monkeypatch):
    settings_svc = MagicMock()
    settings_svc.get_base_domain.return_value = "lab.local"
    settings_svc.get.return_value = "lab.local"
    traefik_svc = MagicMock()
    _override(monkeypatch, settings_svc, traefik_svc)
    try:
        resp = _authed_client().post("/settings/reset")
        assert resp.status_code == 200
        assert "Padrão do ambiente restaurado" in resp.text
        settings_svc.reset_base_domain.assert_called_once()
        traefik_svc.rewrite_base_domain.assert_called_once_with("lab.local", "home.arpa")
    finally:
        app.dependency_overrides.clear()
```

Adicionar em `tests/test_routers.py`, dentro de `test_dashboard_renders_routes_with_base_domain` (e importar `get_effective_base_domain`):

```python
app.dependency_overrides[get_effective_base_domain] = lambda: "lab.local"
# dentro do try, após as asserções existentes:
assert "jellyfin.lab.local" in resp.text
assert 'href="/settings"' in resp.text
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings_router.py -v`
Expected: FAIL com `ModuleNotFoundError: app.routers.settings`.

- [ ] **Step 3: Implementar o router `app/routers/settings.py`**

Criar `APIRouter(prefix="/settings", tags=["settings"])` com:

- Helper de contexto que calcula `default = get_settings().base_domain`, `current = settings_svc.get_base_domain(default)`, `is_custom = settings_svc.get(GLOBAL_SCOPE, BASE_DOMAIN_KEY) is not None`.
- `GET ""` autenticado → `settings.html`.
- `POST ""` autenticado: guarda `previous = settings_svc.get(GLOBAL_SCOPE, BASE_DOMAIN_KEY)` e `old = settings_svc.get_base_domain(default)`; `new = settings_svc.set_base_domain(base_domain)`; se `new != old`, chama `traefik_svc.rewrite_base_domain(old, new)`. Em `ValueError`, mensagem de hostname inválido (sem persistir). Em outra exceção, restaura `previous` (ou `reset_base_domain()` se era `None`) e retorna erro de migração. Sucesso: `message="Configurações salvas"`. Responder com o partial.
- `POST "/reset"` autenticado: `old = settings_svc.get_base_domain(default)`; `reset_base_domain()`; se `old != default`, `rewrite_base_domain(old, default)`; em exceção, restaura `old` com `set_base_domain` e retorna erro; sucesso `message="Padrão do ambiente restaurado"`.

- [ ] **Step 4: Criar os templates**

`app/templates/settings.html`: estende `base.html`; cabeçalho no estilo do `docker.html` com marca StackPilot e links `/` (Dashboard), `/docker` (Docker), `/settings` (Configurações, ativo), `user` e botão de logout; `<main>` com título "Configurações Gerais", `{% include "partials/settings_general_form.html" %}` e um card discreto "Aparência e idioma estarão disponíveis aqui em breve." (sem campos).

`app/templates/partials/settings_general_form.html`: `<div id="settings-general">` com card contendo:
- Título "Geral".
- Mensagem de `message` (verde) e `error` (vermelho) quando presentes.
- `<form hx-post="/settings" hx-target="#settings-general" hx-swap="outerHTML">` com `<input type="text" name="base_domain" value="{{ base_domain }}" required>`, texto do padrão (`default_base_domain`), badge "Personalizado" quando `is_custom` senão "Padrão do .env", botão "Salvar".
- Segundo `<form hx-post="/settings/reset" hx-target="#settings-general" hx-swap="outerHTML">` com botão "Restaurar padrão".

- [ ] **Step 5: Integrar em `main.py` e `routes.py`**

- `app/main.py`: importar e incluir `settings as settings_router`; no dashboard, adicionar `base_domain: str = Depends(get_effective_base_domain)` e usar no contexto no lugar de `settings.base_domain`.
- `app/routers/routes.py`: em cada handler que usa `get_settings().base_domain`, receber `base_domain: str = Depends(get_effective_base_domain)` e passar esse valor ao contexto HTMX.

- [ ] **Step 6: Adicionar links de navegação**

- `app/templates/dashboard.html`: na sidebar, adicionar `<a href="/settings">Configurações</a>` (com ícone de engrenagem) no grupo de navegação; adicionar o mesmo link no drawer mobile.
- `app/templates/docker.html`: adicionar `<a href="/settings">Configurações</a>` ao lado do link Dashboard no topo.

- [ ] **Step 7: Rodar os testes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings_router.py tests/test_routers.py -v`
Expected: PASS.

- [ ] **Step 8: Rodar a suíte completa**

Run: `.venv\Scripts\python.exe -m pytest -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/routers/settings.py app/templates/settings.html app/templates/partials/settings_general_form.html app/main.py app/routers/routes.py app/templates/dashboard.html app/templates/docker.html tests/test_settings_router.py tests/test_routers.py
git commit -m "feat: add general settings page with editable base hostname"
```

---

## Self-Review

- **Cobertura da spec:** armazenamento SQLite (Task 2), fallback `.env` (Task 2/3), aplicação imediata (Task 3/5), migração de rotas (Task 4/5), página e reset (Task 5), extensibilidade por `scope`/chave (Task 2), testes (todas as tasks). Sem lacunas.
- **Tipos/signatures:** `get_effective_base_domain`, `SettingsService.get_base_domain(default)`, `rewrite_base_domain(old, new)` são consistentes entre tasks.
- **Review Focus:** as cinco linhas têm teste nas tasks 1–5.
