# Remover Traefik e focar em containers/imagens — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remover todo o roteamento Traefik e completar o gerenciamento de imagens Docker (remover e pull) com confirmação via Alpine.js.

**Architecture:** O app FastAPI perde os routers/serviços de rotas e configurações, mantendo apenas containers, compose e Docker Hub. `DockerService` ganha `remove_image`/`pull_image`, expostos por endpoints HTMX que re-renderizam `partials/image_list.html`. O frontend usa HTMX + Alpine.js (CDN).

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, HTMX 2, Alpine.js 3, Tailwind CDN, docker-py, pytest.

**Spec:** `docs/superpowers/specs/2026-11-19-remove-traefik-focus-docker-design.md`

## Global Constraints

- Frontend sem Node.js/npm: HTMX e Alpine.js via CDN.
- Confirmação obrigatória (modal Alpine) antes de remover imagem.
- Manter tema escuro estilo Portainer e o padrão HTMX existente.
- Não adicionar streaming de progresso de pull nem autenticação de registry.
- Todos os comandos de teste: `pytest` na raiz do repositório.

## Review Focus

- Remover uma imagem em uso por container deve falhar com mensagem amigável, não derrubar a lista.
- Pull de referência inválida/inexistente deve mostrar erro inline sem perder a lista de imagens.
- Imagem sem tag (`<none>`) deve poder ser removida (referência pelo ID).
- Remover o Traefik não pode quebrar o boot do app (imports de routers/serviços removidos em todos os pontos).
- Docker indisponível durante remove/pull deve retornar erro na parcial, não 500.

---

### Task 1: Remover backend do Traefik (rotas, settings, config, main)

**Files:**
- Delete: `app/routers/routes.py`, `app/services/traefik_service.py`, `app/routers/settings.py`, `app/services/settings_service.py`
- Delete: `tests/test_traefik_service.py`, `tests/test_settings_service.py`, `tests/test_settings_router.py`, `tests/test_dependencies.py`
- Modify: `app/config.py` (remove `traefik_dynamic_dir`, `base_domain`, `normalize_base_domain`, validador)
- Modify: `app/dependencies.py` (remove `get_traefik_service`, `get_effective_base_domain`, `get_settings_service`, imports)
- Modify: `app/main.py` (remove routers/rotas/dependências de Traefik; dashboard carrega só containers e contagem de imagens)
- Modify: `tests/test_config.py` (remover testes de base domain; ajustar teste de paths)
- Modify: `tests/test_routers.py` (remover imports/testes de rota; ajustar teste do dashboard)

**Interfaces:**
- Produces: `app.config.Settings` sem `base_domain`/`traefik_dynamic_dir`.
- Produces: dashboard `GET /` com contexto `containers`, `container_error`, `images_count`, `images_error`, `running_containers`, `stopped_containers`, `stacks_count`, `user`.

- [ ] **Step 1: Atualizar `tests/test_config.py`**

Substituir os testes de base domain por um teste que garanta que a config não expõe mais o campo, e ajustar o teste de paths:

```python
def test_settings_reads_paths_from_env(monkeypatch, tmp_path):
    stacks = tmp_path / "stacks"
    monkeypatch.setenv("STACKS_DIR", str(stacks))
    settings = Settings()
    assert settings.stacks_dir == stacks
    assert not hasattr(settings, "traefik_dynamic_dir")
```

Remover `test_settings_base_domain_default`, `test_settings_normalizes_base_domain`, `test_settings_rejects_invalid_base_domain`, `test_normalize_base_domain_*` e o import de `ValidationError`.

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `pytest tests/test_config.py -q`
Expected: FAIL em `hasattr`/imports (campo ainda existe e `normalize_base_domain` ainda é importado).

- [ ] **Step 3: Ajustar `app/config.py`**

Remover `normalize_base_domain`, o campo `traefik_dynamic_dir`, `base_domain` e o `@field_validator`. Remover o import `field_validator`. Manter as demais configurações intactas.

- [ ] **Step 4: Ajustar `app/dependencies.py`**

Remover imports de `SettingsService` e `TraefikService` e as funções `get_settings_service`, `get_effective_base_domain`, `get_traefik_service`. Manter `get_hub_cache`, `get_dockerhub_service`, `get_docker_service`, `get_compose_service`.

- [ ] **Step 5: Ajustar `app/main.py`**

Remover imports de `get_effective_base_domain`, `get_traefik_service`, `routes_router`, `settings_router`, `TraefikService`; remover `app.include_router(...)` de ambos. No dashboard, trocar a assinatura para:

```python
def dashboard(
    request: Request,
    user: str = Depends(require_auth),
    docker_svc=Depends(get_docker_service),
):
```

Carregar containers e imagens com try/except `DockerUnavailableError`, calcular `images_count = len(images)` e renderizar sem `routes`/`route_error`/`base_domain`.

- [ ] **Step 6: Deletar arquivos e testes do Traefik/settings**

```powershell
Remove-Item app\routers\routes.py, app\services\traefik_service.py, app\routers\settings.py, app\services\settings_service.py
Remove-Item tests\test_traefik_service.py, tests\test_settings_service.py, tests\test_settings_router.py, tests\test_dependencies.py
```

- [ ] **Step 7: Ajustar `tests/test_routers.py`**

Remover imports `get_effective_base_domain`, `get_traefik_service`, `RouteConfig`; remover `test_create_and_delete_route`, `test_create_route_rejects_dotted_subdomain`, `test_edit_route_form_uses_subdomain`. Atualizar o teste do dashboard:

```python
def test_dashboard_renders_containers_and_images_metric():
    mock_docker = MagicMock()
    mock_docker.list_containers.return_value = [
        ContainerInfo(id="1234567890ab", short_id="1234567890ab", name="jellyfin",
                      image="jellyfin/jellyfin:latest", status="running")
    ]
    mock_docker.list_images.return_value = []
    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    try:
        resp = _authed_client().get("/")
        assert resp.status_code == 200
        assert "jellyfin" in resp.text
        assert "Compose Stacks" in resp.text
        assert "Imagens" in resp.text
        assert "Traefik Routes" not in resp.text
        assert 'href="/settings"' not in resp.text
        assert 'href="/docker"' in resp.text
        assert 'href="/static/favicon.svg"' in resp.text
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 8: Rodar a suíte**

Run: `pytest -q`
Expected: PASS (exceto se ainda houver referência a Traefik em templates/deploy, tratadas nas próximas tasks — o backend deve estar limpo).

- [ ] **Step 9: Commit**

```bash
git add -A app/config.py app/dependencies.py app/main.py app/routers app/services tests
git commit -m "refactor: remove traefik routing backend"
```

---

### Task 2: Remover UI do Traefik e adicionar métrica de imagens

**Files:**
- Delete: `app/templates/settings.html`, `app/templates/partials/settings_general_form.html`, `app/templates/partials/route_list.html`, `app/templates/partials/route_edit_row.html`
- Modify: `app/templates/dashboard.html` (remover nav "Configurações"/"Traefik Routes", seção de rotas, form de rota; trocar card de rotas por card de imagens)
- Modify: `app/templates/docker.html` (remover link "Configurações")

**Interfaces:**
- Consumes: contexto do dashboard de Task 1 (`images_count`).
- Produces: dashboard sem qualquer link/seção de Traefik ou `/settings`.

- [ ] **Step 1: Ajustar `tests/test_routers.py`**

O teste `test_dashboard_renders_containers_and_images_metric` (Task 1) já exige `"Traefik Routes" not in resp.text` e `href="/settings"` ausente. Nenhum teste novo.

- [ ] **Step 2: Rodar o teste para ver falhar**

Run: `pytest tests/test_routers.py::test_dashboard_renders_containers_and_images_metric -q`
Expected: FAIL (template ainda contém "Traefik Routes" e `/settings`).

- [ ] **Step 3: Editar `app/templates/dashboard.html`**

Remover o `<li>` de Configurações, o grupo "Rede & Roteamento" inteiro, o link mobile de Traefik, o card "Traefik Routes" (substituir por card "Imagens" usando `{{ images_count }}` e texto "Imagens locais") e a `<section id="routes-section">` completa.

- [ ] **Step 4: Editar `app/templates/docker.html`**

Remover o link `<a href="/settings">` do header.

- [ ] **Step 5: Deletar templates**

```powershell
Remove-Item app\templates\settings.html, app\templates\partials\settings_general_form.html, app\templates\partials\route_list.html, app\templates\partials\route_edit_row.html
```

- [ ] **Step 6: Rodar a suíte**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add -A app/templates
git commit -m "refactor: remove traefik routing UI"
```

---

### Task 3: Limpar deploy, compose, env e documentação

**Files:**
- Delete: `deploy/docker-compose.traefik.yml`
- Modify: `docker-compose.yml` (remover serviço `traefik`, volume `traefik_dynamic`, `depends_on` e mount do diretório dinâmico)
- Modify: `deploy/provision-wsl.sh` (remover `TRAEFIK_DYNAMIC_DIR`, criar só `STACKS_DIR` e rede `stackpilot_net`)
- Modify: `deploy/install-stackpilot.sh` (remover checagem/criação de `TRAEFIK_DYNAMIC_DIR` e o `docker compose ... traefik up`)
- Modify: `.env.example`, `.env.wsl.example` (remover `TRAEFIK_DYNAMIC_DIR` e `BASE_DOMAIN`)
- Modify: `README.md`, `docs/deploy-wsl.md`
- Modify: `tests/test_deployment_assets.py`

**Interfaces:**
- Consumes: nada das tasks anteriores.
- Produces: deploy sem qualquer artefato Traefik.

- [ ] **Step 1: Reescrever `tests/test_deployment_assets.py`**

Remover o load de `deploy/docker-compose.traefik.yml` e os testes `test_traefik_*`. Manter/ajustar:

```python
def test_env_wsl_example_has_required_keys_and_absolute_paths():
    env = _env_map(ENV_WSL)
    for key in ("STACKPILOT_USER", "STACKPILOT_PASSWORD", "SECRET_KEY", "STACKS_DIR"):
        assert key in env
    assert "TRAEFIK_DYNAMIC_DIR" not in env
    assert "BASE_DOMAIN" not in env
    assert env["STACKS_DIR"].startswith("/")

def test_install_script_has_required_logic():
    text = Path("deploy/install-stackpilot.sh").read_text(encoding="utf-8")
    for needle in ("uv venv", "uv pip install", ".env.wsl.example",
                   "stackpilot.service.template",
                   "systemctl enable --now stackpilot.service"):
        assert needle in text
    assert "docker-compose.traefik.yml" not in text
    assert "TRAEFIK_DYNAMIC_DIR" not in text

def test_provision_script_has_required_logic():
    text = Path("deploy/provision-wsl.sh").read_text(encoding="utf-8")
    for needle in ("set -euo pipefail", "systemd=true", "docker-ce",
                   "docker-compose-plugin", "usermod -aG docker",
                   "stackpilot_net", "uv python install"):
        assert needle in text
    assert "TRAEFIK_DYNAMIC_DIR" not in text

def test_readme_focuses_on_containers_and_images():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "Traefik" not in text
    assert "BASE_DOMAIN" not in text
    assert "Docker Hub" in text

def test_root_compose_has_no_traefik():
    data = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    assert "traefik" not in data["services"]
    assert "./data:/opt/stackpilot" in data["services"]["stackpilot"]["volumes"]
```

Manter os testes de unit systemd e do doc WSL (ajustando needles que citam Traefik).

- [ ] **Step 2: Rodar os testes para ver falhar**

Run: `pytest tests/test_deployment_assets.py -q`
Expected: FAIL (README/scripts/compose ainda citam Traefik).

- [ ] **Step 3: Editar `docker-compose.yml`**

Deixar apenas o serviço `stackpilot` (build, porta 8000, env_file, socket, `./stacks:/opt/stacks`, `./data:/opt/stackpilot`, rede `internal`). Remover serviço/volume `traefik*` e `depends_on`.

- [ ] **Step 4: Editar scripts de deploy**

- `provision-wsl.sh`: remover a variável e o diretório `TRAEFIK_DYNAMIC_DIR`; `install -d` só com `$STACKS_DIR`; manter `docker network create stackpilot_net`.
- `install-stackpilot.sh`: remover `TRAEFIK_DYNAMIC_DIR_VALUE`, a checagem de `.env` que depende dele, criar só `$STACKS_DIR_VALUE`, e remover a linha `docker compose ... docker-compose.traefik.yml up -d`.

- [ ] **Step 5: Editar `.env.example` e `.env.wsl.example`**

Remover as linhas `TRAEFIK_DYNAMIC_DIR=...` e `BASE_DOMAIN=home.arpa`. Manter `STACKS_DIR`, `HUB_DB_PATH`, `HUB_CACHE_TTL_SECONDS`, `COMPOSE_UP_TIMEOUT_SECONDS`, `STACKPILOT_NETWORK`.

- [ ] **Step 6: Deletar e atualizar docs**

```powershell
Remove-Item deploy\docker-compose.traefik.yml
```

Em `README.md`: remover "roteamento com Traefik" da descrição, o bullet de rotas, entradas de arquitetura (`routes.py`, `traefik_service.py`, settings), requisito do Traefik e variáveis `TRAEFIK_DYNAMIC_DIR`/`BASE_DOMAIN`; descrever gerenciamento de imagens (remover/pull).

Em `docs/deploy-wsl.md`: remover a seção "Traefik e rotas", menções ao Traefik no passo 2/5/7 e `BASE_DOMAIN`; manter instalação do Docker, rede `stackpilot_net`, systemd e acesso em `http://localhost:8000`.

- [ ] **Step 7: Rodar a suíte**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add -A docker-compose.yml deploy .env.example .env.wsl.example README.md docs tests/test_deployment_assets.py
git commit -m "chore: remove traefik deploy assets and config"
```

---

### Task 4: Ações de imagem no `DockerService`

**Files:**
- Modify: `app/services/docker_service.py`
- Test: `tests/test_docker_service.py`

**Interfaces:**
- Produces: `DockerService.remove_image(ref: str, force: bool = False) -> None`
- Produces: `DockerService.pull_image(ref: str) -> None`
- Produces: exceções `ImageNotFoundError`, `ImageInUseError`, `ImagePullError`

- [ ] **Step 1: Escrever os testes que falham em `tests/test_docker_service.py`**

Adicionar imports `APIError`, `ImageNotFound` e as novas exceções, e os testes:

```python
def test_remove_image_calls_docker():
    client = MagicMock()
    DockerService(client=client).remove_image("nginx:alpine", force=True)
    client.images.remove.assert_called_once_with("nginx:alpine", force=True)


def test_remove_image_not_found():
    client = MagicMock()
    client.images.remove.side_effect = ImageNotFound("missing")
    with pytest.raises(ImageNotFoundError):
        DockerService(client=client).remove_image("missing:tag")


def test_remove_image_in_use():
    client = MagicMock()
    client.images.remove.side_effect = APIError(
        "conflict: unable to remove repository reference (must force) - container is using its referenced image"
    )
    with pytest.raises(ImageInUseError):
        DockerService(client=client).remove_image("nginx:alpine")


def test_pull_image_calls_docker():
    client = MagicMock()
    DockerService(client=client).pull_image("nginx:alpine")
    client.images.pull.assert_called_once_with("nginx:alpine")


def test_pull_image_failure():
    client = MagicMock()
    client.images.pull.side_effect = APIError("pull access denied")
    with pytest.raises(ImagePullError):
        DockerService(client=client).pull_image("private/img:latest")
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest tests/test_docker_service.py -q`
Expected: FAIL (`ImportError` dos nomes novos).

- [ ] **Step 3: Implementar em `app/services/docker_service.py`**

Adicionar as exceções ao lado de `DockerUnavailableError`. Implementar:

```python
def remove_image(self, ref: str, force: bool = False) -> None:
    try:
        self._get_client().images.remove(ref, force=force)
    except NotFound as exc:
        raise ImageNotFoundError(f"Imagem '{ref}' não encontrada") from exc
    except APIError as exc:
        message = str(exc).lower()
        if exc.status_code == 409 or "in use" in message or "being used" in message:
            raise ImageInUseError(
                f"Imagem '{ref}' está em uso por um container; pare/remova o container antes."
            ) from exc
        raise DockerUnavailableError(f"Falha ao remover imagem: {exc}") from exc
    except DockerException as exc:
        raise DockerUnavailableError(f"Docker daemon unavailable: {exc}") from exc

def pull_image(self, ref: str) -> None:
    try:
        self._get_client().images.pull(ref)
    except NotFound as exc:
        raise ImagePullError(f"Imagem '{ref}' não encontrada no registry") from exc
    except APIError as exc:
        raise ImagePullError(f"Falha ao baixar imagem '{ref}': {exc}") from exc
    except DockerException as exc:
        raise DockerUnavailableError(f"Docker daemon unavailable: {exc}") from exc
```

Importar `APIError`, `ImageNotFound` de `docker.errors`.

- [ ] **Step 4: Rodar os testes**

Run: `pytest tests/test_docker_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/docker_service.py tests/test_docker_service.py
git commit -m "feat: add docker image remove and pull actions"
```

---

### Task 5: Endpoints HTMX e UI de imagens (HTMX + Alpine)

**Files:**
- Modify: `app/routers/docker.py`
- Modify: `app/templates/base.html`
- Modify: `app/templates/partials/image_list.html`
- Test: `tests/test_docker_router.py`

**Interfaces:**
- Consumes: `DockerService.remove_image`, `pull_image`, exceções de Task 4.
- Produces: `POST /docker/images/remove` (form `image`, `force` opcional) e `POST /docker/images/pull` (form `image`), ambos retornando `partials/image_list.html` com `message`/`error`.

- [ ] **Step 1: Escrever os testes que falham em `tests/test_docker_router.py`**

```python
from app.services.docker_service import ImageInUseError, ImagePullError

def _image_override(mock_docker, mock_cache=None):
    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    app.dependency_overrides[get_hub_cache] = lambda: (mock_cache or MagicMock(
        list_used_images=MagicMock(return_value=[])))
    mock_docker.list_images.return_value = []


def test_remove_image_endpoint_refreshes_list():
    mock_docker = MagicMock()
    _image_override(mock_docker)
    try:
        r = _client().post("/docker/images/remove", data={"image": "nginx:alpine"})
        assert r.status_code == 200
        mock_docker.remove_image.assert_called_once_with("nginx:alpine", force=False)
        assert "removida" in r.text.lower()
    finally:
        app.dependency_overrides.clear()


def test_remove_image_in_use_shows_error():
    mock_docker = MagicMock()
    mock_docker.remove_image.side_effect = ImageInUseError("em uso por container")
    _image_override(mock_docker)
    try:
        r = _client().post("/docker/images/remove", data={"image": "nginx:alpine"})
        assert r.status_code == 200
        assert "em uso por container" in r.text
    finally:
        app.dependency_overrides.clear()


def test_pull_image_endpoint_refreshes_list():
    mock_docker = MagicMock()
    _image_override(mock_docker)
    try:
        r = _client().post("/docker/images/pull", data={"image": "nginx:alpine"})
        assert r.status_code == 200
        mock_docker.pull_image.assert_called_once_with("nginx:alpine")
        assert "baixada" in r.text.lower()
    finally:
        app.dependency_overrides.clear()


def test_pull_image_error_shows_message():
    mock_docker = MagicMock()
    mock_docker.pull_image.side_effect = ImagePullError("falha ao baixar")
    _image_override(mock_docker)
    try:
        r = _client().post("/docker/images/pull", data={"image": "bad/image"})
        assert r.status_code == 200
        assert "falha ao baixar" in r.text
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest tests/test_docker_router.py -q`
Expected: FAIL (endpoints 404).

- [ ] **Step 3: Implementar os endpoints em `app/routers/docker.py`**

Adicionar `_render_images` helper e as rotas:

```python
@router.post("/docker/images/remove", response_class=HTMLResponse)
def remove_image(
    request: Request,
    image: str = Form(...),
    force: bool = Form(False),
    user: str = Depends(require_auth),
    docker_svc: DockerService = Depends(get_docker_service),
    hub_cache: HubCache = Depends(get_hub_cache),
):
    message = error = None
    ref = image.strip()
    try:
        docker_svc.remove_image(ref, force=force)
        message = f"Imagem {ref} removida."
    except (ImageNotFoundError, ImageInUseError, DockerUnavailableError) as exc:
        error = str(exc)
    images, used_images, images_error = _load_images(docker_svc, hub_cache)
    return templates.TemplateResponse(
        request,
        "partials/image_list.html",
        {"images": images, "used_images": used_images,
         "images_error": images_error, "message": message, "error": error},
    )

@router.post("/docker/images/pull", response_class=HTMLResponse)
def pull_image(
    request: Request,
    image: str = Form(...),
    user: str = Depends(require_auth),
    docker_svc: DockerService = Depends(get_docker_service),
    hub_cache: HubCache = Depends(get_hub_cache),
):
    message = error = None
    ref = image.strip()
    try:
        docker_svc.pull_image(ref)
        message = f"Imagem {ref} baixada/atualizada."
    except (ImagePullError, DockerUnavailableError) as exc:
        error = str(exc)
    images, used_images, images_error = _load_images(docker_svc, hub_cache)
    return templates.TemplateResponse(
        request,
        "partials/image_list.html",
        {"images": images, "used_images": used_images,
         "images_error": images_error, "message": message, "error": error},
    )
```

Importar `ImageInUseError`, `ImageNotFoundError`, `ImagePullError` de `docker_service`.

- [ ] **Step 4: Adicionar Alpine.js em `app/templates/base.html`**

No `<head>`, após o script do HTMX:

```html
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
```

- [ ] **Step 5: Reescrever `app/templates/partials/image_list.html`**

Envolver o conteúdo em `<div x-data="{ confirmOpen: false, target: '' }">`. Adicionar:

- Blocos de `message` (verde) e `error` (vermelho).
- Formulário de pull: `<form hx-post="/docker/images/pull" hx-target="#image-list" hx-swap="innerHTML" class="mb-4 flex ...">` com input `name="image"` e botão "Baixar / Atualizar".
- Em cada tag: botão "Atualizar" (`hx-post="/docker/images/pull" hx-target="#image-list" hx-swap="innerHTML" hx-vals='{"image": "{{ tag }}"}') e botão "Remover" (`type="button" @click="target='{{ tag }}'; confirmOpen=true"`).
- Na imagem sem tag: botão "Remover" com `target='{{ img.id }}'`.
- Modal no fim da parcial:

```html
<div x-show="confirmOpen" x-cloak class="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
  <div class="w-full max-w-sm rounded-xl border border-[#232f45] bg-[#161e2e] p-5 space-y-4">
    <h3 class="text-sm font-semibold text-white">Remover imagem?</h3>
    <p class="text-xs text-slate-400">A imagem <span class="font-mono text-slate-200" x-text="target"></span> será removida permanentemente.</p>
    <div class="flex justify-end gap-2">
      <button type="button" @click="confirmOpen=false" class="px-3 py-1.5 rounded-lg bg-[#0f1521] border border-[#232f45] text-xs text-slate-200">Cancelar</button>
      <form hx-post="/docker/images/remove" hx-target="#image-list" hx-swap="innerHTML">
        <input type="hidden" name="image" :value="target">
        <button type="submit" class="px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs font-medium">Remover</button>
      </form>
    </div>
  </div>
</div>
```

Adicionar `<style>[x-cloak]{display:none!important}</style>` em `base.html` ou no topo da parcial para evitar flash.

- [ ] **Step 6: Rodar a suíte**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/routers/docker.py app/templates/base.html app/templates/partials/image_list.html tests/test_docker_router.py
git commit -m "feat: add image pull and remove actions to docker page"
```

---

## Self-Review

- **Cobertura do spec:** remoção de rotas/serviço/settings (Tasks 1–2), assets/deploy/docs (Task 3), remove/pull de imagens (Tasks 4–5), confirmação Alpine (Task 5). Coberto.
- **Consistência de tipos:** `remove_image(ref, force)` e `pull_image(ref)` definidos na Task 4 e consumidos com as mesmas assinaturas na Task 5. Exceções `ImageNotFoundError`, `ImageInUseError`, `ImagePullError` consistentes.
- **Review Focus:** imagem em uso, pull inválido, imagem sem tag, boot sem Traefik e Docker indisponível têm testes nas Tasks 4/5 ou verificações diretas nas Tasks 1/3.
- **Proporção:** plano orientado a decisões e testes; corpos de UI completos apenas onde a cópia/estrutura é fixada.
