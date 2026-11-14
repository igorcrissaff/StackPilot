# StackPilot — Deploy nativo em WSL — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rodar o StackPilot nativamente numa distro WSL2 (Python 3.14) com acesso direto ao Docker Engine da mesma distro, mantendo o Traefik como container e o deploy em Docker atual intacto.

**Architecture:** App roda via `systemd` a partir de um venv (`uv` + Python 3.14) e fala com `/var/run/docker.sock` nativo; Traefik sobe por um compose dedicado na rede externa `stackpilot_net`, bind-montando o mesmo diretório dinâmico que o app escreve. Provisionamento do host e instalação do app ficam em scripts em `deploy/`, documentados em `docs/deploy-wsl.md`.

**Tech Stack:** Bash, WSL2, Ubuntu/Debian, Docker Engine (`docker-ce` + `docker-compose-plugin`), `systemd`, `uv`, Python 3.14, pytest, PyYAML.

**Spec:** `docs/superpowers/specs/2026-11-14-native-wsl-deployment-design.md`

## Global Constraints

- Runtime nativo em **Python 3.14**; fallback **3.13** via `PY_VERSION`.
- `docker-ce` + plugin `docker compose` na distro; socket em `/var/run/docker.sock`.
- `systemd` habilitado via `/etc/wsl.conf` (`[boot] systemd=true`).
- Instalação **limpa** — nenhuma migração de rotas/stacks do deploy atual.
- App é `User=<deploy user>` do grupo `docker`; **não** roda como root.
- App e Traefik usam o **mesmo** `TRAEFIK_DYNAMIC_DIR`.
- Traefik na rede externa `stackpilot_net`, `restart: unless-stopped`, `extra_hosts: host.docker.internal:host-gateway`.
- Deploy em container existente (`Dockerfile`, `docker-compose.yml`) continua funcionando sem alteração.
- `requires-python` do `pyproject.toml` permanece `>=3.11`.

## Review Focus

- Serviço `systemd` sobe antes do Docker e não enxerga o socket → unidade precisa de `After=`/`Wants= docker.service` (Task 3).
- `.env` com paths relativos ou divergentes → app grava fora do bind mount do Traefik; paths devem ser absolutos e refletir `APP_DIR` (Task 2, Task 5).
- Rede externa `stackpilot_net` ausente → `docker compose up` do Traefik falha; provisionamento deve criá-la (Task 4).
- Usuário fora do grupo `docker` → 403 no socket; provisionamento adiciona ao grupo e docs exigem novo login (Task 4, Task 6).
- Distro sem `systemd` ativo → `systemctl` falha; provisionamento grava `wsl.conf` e instrui `wsl --shutdown` (Task 4, Task 6).

---

## File Structure

- `deploy/provision-wsl.sh` — provisionamento do host (systemd, Docker, rede, uv, Python, grupo docker, diretórios).
- `deploy/docker-compose.traefik.yml` — Traefik v3 standalone com bind mount e rede externa.
- `deploy/stackpilot.service.template` — unidade `systemd` com placeholders `__USER__` / `__APP_DIR__`.
- `deploy/install-stackpilot.sh` — venv, dependências, `.env`, render/ativação do serviço, sobe Traefik.
- `.env.wsl.example` — env de referência com paths absolutos da WSL.
- `tests/test_deployment_assets.py` — valida assets de deploy (YAML, env, unidade, scripts).
- `tests/test_config.py` — adiciona verificação de paths via env.
- `docs/deploy-wsl.md` — guia passo a passo.
- `README.md` — link para o guia.

---

### Task 1: Traefik compose standalone

**Files:**
- Create: `deploy/docker-compose.traefik.yml`
- Test: `tests/test_deployment_assets.py`

**Interfaces:**
- Produces: arquivo compose com serviço `traefik`, rede externa `stackpilot_net`, volume `${TRAEFIK_DYNAMIC_DIR}:/etc/traefik/dynamic`.

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

import yaml

COMPOSE = Path("deploy/docker-compose.traefik.yml")


def _traefik() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_traefik_compose_service_and_restart():
    svc = _traefik()["services"]["traefik"]
    assert svc["image"].startswith("traefik:v3")
    assert svc["restart"] == "unless-stopped"
    assert "host.docker.internal:host-gateway" in svc["extra_hosts"]


def test_traefik_compose_external_network():
    net = _traefik()["networks"]["internal"]
    assert net["name"] == "stackpilot_net"
    assert net["external"] is True


def test_traefik_compose_binds_dynamic_dir_and_ports():
    traefik = _traefik()["services"]["traefik"]
    volumes = traefik["volumes"]
    assert any(v.endswith(":/etc/traefik/dynamic") for v in volumes)
    assert any("${TRAEFIK_DYNAMIC_DIR:" in v for v in volumes)
    for port in ("80:80", "443:443", "8080:8080"):
        assert port in traefik["ports"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_deployment_assets.py -v`
Expected: FAIL — `FileNotFoundError` for `deploy/docker-compose.traefik.yml`.

- [ ] **Step 3: Create `deploy/docker-compose.traefik.yml`**

```yaml
services:
  traefik:
    image: traefik:v3.0
    container_name: traefik
    restart: unless-stopped
    command:
      - "--api.insecure=true"
      - "--api.dashboard=true"
      - "--providers.file.directory=/etc/traefik/dynamic"
      - "--providers.file.watch=true"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
    ports:
      - "80:80"
      - "443:443"
      - "8080:8080"
    volumes:
      - ${TRAEFIK_DYNAMIC_DIR:-/opt/stackpilot/data/traefik/dynamic}:/etc/traefik/dynamic
    extra_hosts:
      - "host.docker.internal:host-gateway"
    networks:
      - internal

networks:
  internal:
    name: stackpilot_net
    external: true
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_deployment_assets.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add deploy/docker-compose.traefik.yml tests/test_deployment_assets.py
git commit -m "feat: add standalone Traefik compose for native WSL deploy"
```

---

### Task 2: Env de referência e paths via ambiente

**Files:**
- Create: `.env.wsl.example`
- Modify: `tests/test_config.py`
- Test: `tests/test_deployment_assets.py`

**Interfaces:**
- Produces: `.env.wsl.example` com `STACKPILOT_USER`, `STACKPILOT_PASSWORD`, `SECRET_KEY`, `TRAEFIK_DYNAMIC_DIR`, `STACKS_DIR` (os dois últimos absolutos).

- [ ] **Step 1: Write the failing tests**

Adicione em `tests/test_deployment_assets.py`:

```python
ENV_WSL = Path(".env.wsl.example")


def _env_map(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def test_env_wsl_example_has_required_keys_and_absolute_paths():
    env = _env_map(ENV_WSL)
    for key in (
        "STACKPILOT_USER",
        "STACKPILOT_PASSWORD",
        "SECRET_KEY",
        "TRAEFIK_DYNAMIC_DIR",
        "STACKS_DIR",
    ):
        assert key in env
    assert env["TRAEFIK_DYNAMIC_DIR"].startswith("/")
    assert env["STACKS_DIR"].startswith("/")
```

Adicione em `tests/test_config.py`:

```python
def test_settings_reads_paths_from_env(monkeypatch, tmp_path):
    dynamic = tmp_path / "traefik-dynamic"
    stacks = tmp_path / "stacks"
    monkeypatch.setenv("TRAEFIK_DYNAMIC_DIR", str(dynamic))
    monkeypatch.setenv("STACKS_DIR", str(stacks))
    settings = Settings()
    assert settings.traefik_dynamic_dir == dynamic
    assert settings.stacks_dir == stacks
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_deployment_assets.py tests/test_config.py -v`
Expected: FAIL — `.env.wsl.example` ausente e paths não lidos.

- [ ] **Step 3: Create `.env.wsl.example`**

```dotenv
STACKPILOT_USER=admin
STACKPILOT_PASSWORD=admin
SECRET_KEY=change-me-in-production
TRAEFIK_DYNAMIC_DIR=/opt/stackpilot/data/traefik/dynamic
STACKS_DIR=/opt/stackpilot/data/stacks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_deployment_assets.py tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .env.wsl.example tests/test_deployment_assets.py tests/test_config.py
git commit -m "feat: add WSL env example and verify path wiring"
```

---

### Task 3: Unidade systemd (template)

**Files:**
- Create: `deploy/stackpilot.service.template`
- Test: `tests/test_deployment_assets.py`

**Interfaces:**
- Produces: template com placeholders `__USER__` e `__APP_DIR__`; `ExecStart=__APP_DIR__/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`.

- [ ] **Step 1: Write the failing test**

Adicione em `tests/test_deployment_assets.py`:

```python
UNIT = Path("deploy/stackpilot.service.template")


def test_systemd_unit_template_directives():
    text = UNIT.read_text(encoding="utf-8")
    for needle in (
        "[Unit]",
        "[Service]",
        "[Install]",
        "User=__USER__",
        "WorkingDirectory=__APP_DIR__",
        "EnvironmentFile=__APP_DIR__/.env",
        "ExecStart=__APP_DIR__/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000",
        "Restart=on-failure",
        "After=network-online.target docker.service",
        "Wants=network-online.target docker.service",
        "WantedBy=multi-user.target",
    ):
        assert needle in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_deployment_assets.py::test_systemd_unit_template_directives -v`
Expected: FAIL — arquivo ausente.

- [ ] **Step 3: Create `deploy/stackpilot.service.template`**

```ini
[Unit]
Description=StackPilot control panel
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
Type=simple
User=__USER__
WorkingDirectory=__APP_DIR__
EnvironmentFile=__APP_DIR__/.env
ExecStart=__APP_DIR__/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_deployment_assets.py::test_systemd_unit_template_directives -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deploy/stackpilot.service.template tests/test_deployment_assets.py
git commit -m "feat: add systemd unit template for StackPilot"
```

---

### Task 4: Script de provisionamento do host

**Files:**
- Create: `deploy/provision-wsl.sh`
- Test: `tests/test_deployment_assets.py`

**Interfaces:**
- Consumes: nada.
- Produces: script executável que, como root, habilita systemd, instala Docker Engine + compose plugin, adiciona o usuário ao grupo `docker`, instala `uv` + Python, cria diretórios de dados e a rede `stackpilot_net`.

- [ ] **Step 1: Write the failing test**

Adicione em `tests/test_deployment_assets.py`:

```python
def test_provision_script_has_required_logic():
    text = Path("deploy/provision-wsl.sh").read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert "systemd=true" in text
    assert "wsl --shutdown" in text
    assert "docker-ce" in text
    assert "docker-compose-plugin" in text
    assert "usermod -aG docker" in text
    assert "stackpilot_net" in text
    assert "uv python install" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_deployment_assets.py::test_provision_script_has_required_logic -v`
Expected: FAIL — arquivo ausente.

- [ ] **Step 3: Create `deploy/provision-wsl.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo ./deploy/provision-wsl.sh" >&2
  exit 1
fi

DEPLOY_USER="${STACKPILOT_USER:-${SUDO_USER:-root}}"
APP_DIR="${APP_DIR:-/opt/stackpilot}"
TRAEFIK_DYNAMIC_DIR="${TRAEFIK_DYNAMIC_DIR:-$APP_DIR/data/traefik/dynamic}"
STACKS_DIR="${STACKS_DIR:-$APP_DIR/data/stacks}"
PY_VERSION="${PY_VERSION:-3.14}"

# 1. Enable systemd in WSL
if ! grep -q '^systemd=true' /etc/wsl.conf 2>/dev/null; then
  printf '\n[boot]\nsystemd=true\n' >> /etc/wsl.conf
fi
if [ "$(ps -p 1 -o comm= 2>/dev/null)" != "systemd" ]; then
  echo "systemd habilitado em /etc/wsl.conf."
  echo "No Windows, rode 'wsl --shutdown' e reabra a distro; depois rode este script de novo." >&2
  exit 1
fi

# 2. Base packages
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg

# 3. Docker Engine from the official repository
. /etc/os-release
install -m 0755 -d /etc/apt/keyrings
curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker

# 4. Docker group for the deploy user
groupadd -f docker
usermod -aG docker "$DEPLOY_USER"

# 5. uv (system-wide) and Python for the deploy user
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  install -m 0755 /root/.local/bin/uv /usr/local/bin/uv
fi
sudo -u "$DEPLOY_USER" -H /usr/local/bin/uv python install "$PY_VERSION"

# 6. Data directories and external network
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$TRAEFIK_DYNAMIC_DIR" "$STACKS_DIR"
docker network inspect stackpilot_net >/dev/null 2>&1 || docker network create stackpilot_net

echo "Host provisionado. Usuário '$DEPLOY_USER' precisa de novo login para o grupo docker."
```

- [ ] **Step 4: Make executable and verify syntax**

Run: `bash -n deploy/provision-wsl.sh`
Expected: sem saída (sintaxe válida).

No Windows, rode esse check dentro da WSL (`wsl bash -n deploy/provision-wsl.sh`).

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_deployment_assets.py::test_provision_script_has_required_logic -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deploy/provision-wsl.sh tests/test_deployment_assets.py
git commit -m "feat: add WSL host provisioning script"
```

---

### Task 5: Script de instalação do StackPilot

**Files:**
- Create: `deploy/install-stackpilot.sh`
- Test: `tests/test_deployment_assets.py`

**Interfaces:**
- Consumes: `deploy/stackpilot.service.template`, `deploy/docker-compose.traefik.yml`, `.env.wsl.example`.
- Produces: script que cria `.venv` (Python `PY_VERSION`), instala deps, gera `.env`, renderiza/ativa o serviço `systemd` e sobe o Traefik.

- [ ] **Step 1: Write the failing test**

Adicione em `tests/test_deployment_assets.py`:

```python
def test_install_script_has_required_logic():
    text = Path("deploy/install-stackpilot.sh").read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert "uv venv" in text
    assert "uv pip install" in text
    assert ".env.wsl.example" in text
    assert "stackpilot.service.template" in text
    assert "systemctl enable --now stackpilot.service" in text
    assert "docker-compose.traefik.yml" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_deployment_assets.py::test_install_script_has_required_logic -v`
Expected: FAIL — arquivo ausente.

- [ ] **Step 3: Create `deploy/install-stackpilot.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  echo "Run as the deploy user (not root)." >&2
  exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${APP_DIR:-$REPO_DIR}"
PY_VERSION="${PY_VERSION:-3.14}"
SERVICE_USER="$(id -un)"

cd "$APP_DIR"
command -v uv >/dev/null 2>&1 || { echo "uv not found; run deploy/provision-wsl.sh first." >&2; exit 1; }

uv python install "$PY_VERSION"
uv venv --python "$PY_VERSION" .venv
uv pip install --python .venv/bin/python -e ".[dev]"

mkdir -p data/traefik/dynamic data/stacks

if [ ! -f .env ]; then
  sed "s#/opt/stackpilot#${APP_DIR}#g" .env.wsl.example > .env
  chmod 600 .env
fi

sed -e "s#__USER__#${SERVICE_USER}#g" -e "s#__APP_DIR__#${APP_DIR}#g" \
  deploy/stackpilot.service.template | sudo tee /etc/systemd/system/stackpilot.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now stackpilot.service

docker compose --env-file "$APP_DIR/.env" -f deploy/docker-compose.traefik.yml up -d

echo "StackPilot ativo. Veja: systemctl status stackpilot"
```

- [ ] **Step 4: Make executable and verify syntax**

Run: `bash -n deploy/install-stackpilot.sh`
Expected: sem saída (sintaxe válida).

No Windows, rode dentro da WSL (`wsl bash -n deploy/install-stackpilot.sh`).

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_deployment_assets.py::test_install_script_has_required_logic -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deploy/install-stackpilot.sh tests/test_deployment_assets.py
git commit -m "feat: add native StackPilot install script"
```

---

### Task 6: Documentação do deploy nativo

**Files:**
- Create: `docs/deploy-wsl.md`
- Modify: `README.md`
- Test: `tests/test_deployment_assets.py`

**Interfaces:**
- Consumes: scripts e arquivos das Tasks 1–5.

- [ ] **Step 1: Write the failing test**

Adicione em `tests/test_deployment_assets.py`:

```python
DOC = Path("docs/deploy-wsl.md")


def test_wsl_deploy_doc_covers_key_steps():
    text = DOC.read_text(encoding="utf-8")
    for needle in (
        "provision-wsl.sh",
        "install-stackpilot.sh",
        "systemctl status stackpilot",
        "networkingMode=mirrored",
        "wsl --shutdown",
        "stackpilot_net",
    ):
        assert needle in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_deployment_assets.py::test_wsl_deploy_doc_covers_key_steps -v`
Expected: FAIL — arquivo ausente.

- [ ] **Step 3: Create `docs/deploy-wsl.md`**

````markdown
# Deploy nativo em WSL2

Roda o StackPilot como processo Python nativo numa distro WSL2, com acesso direto ao Docker Engine da mesma distro. Instalação limpa: rotas e stacks antigas não são migradas.

## Pré-requisitos
- Windows 11 + WSL2 com uma distro Ubuntu ou Debian.
- Acesso `sudo` na distro e o repositório clonado (ex.: `/opt/stackpilot`).

## 1. Provisionar o host
```bash
sudo ./deploy/provision-wsl.sh
```
Na primeira execução o script habilita `systemd` em `/etc/wsl.conf` e para. No Windows:
```
wsl --shutdown
```
Reabra a distro e rode o script de novo. Ele instala `docker-ce` + plugin `docker compose`, adiciona seu usuário ao grupo `docker`, instala `uv` + Python 3.14 (fallback 3.13 com `PY_VERSION=3.13`), cria os diretórios de dados e a rede `stackpilot_net`.

> Saia e entre na distro após o script para o grupo `docker` valer.

## 2. Instalar o StackPilot
```bash
./deploy/install-stackpilot.sh
```
Cria `.venv` com Python 3.14, instala as dependências, gera `.env` a partir de `.env.wsl.example`, registra e ativa o serviço `systemd` e sobe o Traefik.

## 3. Acessar
- App: `http://localhost:8000` (login de `.env`).
- Traefik dashboard: `http://localhost:8080`.

## 4. Rede para a LAN
Por padrão o WSL2 fica atrás de NAT. Em Windows 11, crie `%USERPROFILE%\.wslconfig`:
```ini
[wsl2]
networkingMode=mirrored
```
Rode `wsl --shutdown` e reabra. Alternativa sem mirrored networking: `netsh interface portproxy` para 8000/80/443.

## 5. Iniciar no boot/login do Windows
Crie uma Tarefa Agendada no logon executando:
```
wsl.exe -d <distro> -u root -e systemctl start stackpilot.service
```
O Traefik volta sozinho pelo `restart: unless-stopped` com o `docker.service` habilitado.

## 6. Operação
```bash
systemctl status stackpilot
journalctl -u stackpilot -f
```

## 7. Traefik e rotas
O Traefik entra na rede externa `stackpilot_net`. Rotas apontam para nomes de containers dessa rede; para um serviço no host da WSL, use `http://host.docker.internal:<porta>`. As stacks gerenciadas precisam entrar na `stackpilot_net`.

## Manter o deploy em Docker
O caminho antigo continua válido:
```bash
cp .env.example .env
docker compose up -d
```
````

- [ ] **Step 4: Link from `README.md`**

Adicione abaixo da seção "Rodando com Docker":

```markdown
### Rodando nativamente em WSL2

Veja [docs/deploy-wsl.md](docs/deploy-wsl.md) para rodar o StackPilot como processo nativo numa distro WSL2, com acesso direto ao Docker Engine.
```

- [ ] **Step 5: Run tests and full suite**

Run: `pytest -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/deploy-wsl.md README.md tests/test_deployment_assets.py
git commit -m "docs: add native WSL deployment guide"
```

---

## Final Verification

- [ ] `pytest -v` — suíte completa verde.
- [ ] `wsl bash -n deploy/provision-wsl.sh` e `wsl bash -n deploy/install-stackpilot.sh` — sintaxe válida.
- [ ] Numa WSL de teste: rodar `provision-wsl.sh`, `wsl --shutdown`, reabrir, rodar `install-stackpilot.sh`.
- [ ] `systemctl status stackpilot` ativo; `curl http://localhost:8000/login` retorna 200.
- [ ] Dashboard lista containers do Docker da WSL.
- [ ] Criar rota na UI grava em `TRAEFIK_DYNAMIC_DIR` e o Traefik carrega o arquivo.
- [ ] `docker compose up -d` do compose antigo continua subindo o StackPilot em container.
