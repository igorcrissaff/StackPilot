# StackPilot — Deploy nativo em WSL — Design Document

## 1. Intent & Why
Rodar o StackPilot como processo Python nativo dentro de uma distro WSL2, em vez de container, para falar direto com o Docker Engine daquela mesma VM e, no futuro, expor informações reais do host. O objetivo é eficiência e acesso nativo ao daemon — não orquestração multi-nó.

## 2. Goals, Non-Goals & Anti-Goals
- **Goals:**
  - Rodar o StackPilot nativo (venv + uvicorn) numa distro WSL2, gerenciado por `systemd`.
  - Acessar o Docker Engine instalado na mesma distro via `/var/run/docker.sock`, sem mapeamento de container.
  - Manter o Traefik como container nessa distro, compartilhando o diretório de config dinâmica com o app nativo via bind mount.
  - Preservar o deploy via Docker existente (não quebrar o caminho atual).
  - Provisionar o host WSL de forma reproduzível: `docker-ce` + plugin `docker compose`, `systemd` habilitado e Python **3.14** (fallback 3.13).
  - Entregar artefatos e documentação reproduzíveis de instalação.
- **Non-Goals:**
  - Migrar dados do deploy em Docker atual (rotas/stacks existentes) — a mudança é **instalação limpa**.
  - Métricas nativas de host no dashboard (CPU/RAM/disco/uptime) — adiado.
  - Rodar Traefik como binário nativo.
  - Gerenciar daemons remotos / multi-nó.
  - Caminho com Docker Desktop (opção B).
- **Anti-Goals:**
  - App e Traefik apontando para diretórios diferentes (app escreve onde o Traefik não lê).
  - Exigir `root` para o processo do app.

## 3. Constraints
- Python **3.14** como alvo do runtime nativo (fallback 3.13 se alguma dependência ainda não tiver wheel). FastAPI + Uvicorn, dependências já definidas em `pyproject.toml`. O `requires-python` do projeto pode permanecer `>=3.11` para não quebrar o deploy em container; sobe só se necessário.
- Docker Engine (`docker-ce`) + plugin `docker compose` instalados na WSL, com socket em `/var/run/docker.sock`.
- `systemd` habilitado na distro via `/etc/wsl.conf`.
- WSL2; Windows 11 recomendado para `networkingMode=mirrored` (exposição à LAN).
- Configuração via variáveis de ambiente já suportadas (`TRAEFIK_DYNAMIC_DIR`, `STACKS_DIR`, `STACKPILOT_*`, `SECRET_KEY`).

## 4. Approaches Considered
1. **A — Docker Engine na WSL, StackPilot nativo, Traefik container (escolhido).** Menor overhead, acesso real ao daemon/host da VM, sem Docker Desktop. Custo: instalar/manter Engine, habilitar systemd, resolver exposição de portas.
2. **B — StackPilot nativo + Docker Desktop com integração WSL.** Menos setup, mas o "host" visto é a VM da WSL, mantém overhead do Desktop e não é o daemon nativo da distro. Rejeitado.
3. **C — Variante de A: distro WSL dedicada como "servidor".** É escolha de *onde*, não de *como*: o mesmo caminho A funciona em qualquer distro; recomendado usar uma distro dedicada separada do ambiente de dev.

## 5. Architecture & Key Decisions
### Layout no host (WSL)
```
/opt/stackpilot/                       # checkout do projeto + .venv
/opt/stackpilot/data/traefik/dynamic/  # TRAEFIK_DYNAMIC_DIR (bind mount do Traefik)
/opt/stackpilot/data/stacks/           # STACKS_DIR (compose das stacks)
```
Paths são decisão deste design; podem ser substituídos via `.env`.

### Processo do app
- Executado por `systemd` a partir de um venv em `/opt/stackpilot/.venv`, com `WorkingDirectory=/opt/stackpilot` (garante leitura do `.env` relativo).
- Comando: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- Unidade `deploy/stackpilot.service`: `After=network-online.target docker.service`, `Wants=docker.service`, `Restart=on-failure`, `EnvironmentFile=/opt/stackpilot/.env`, `User=<usuário de deploy>`.
- O usuário do serviço pertence ao grupo `docker` para acessar o socket sem `root`.

### Traefik
- Novo `deploy/docker-compose.traefik.yml` com Traefik v3, ports `80/443/8080`, bind mount `${TRAEFIK_DYNAMIC_DIR}:/etc/traefik/dynamic` (em vez do named volume atual).
- App nativo e Traefik apontam para o **mesmo** diretório de host; é o ponto que evita o anti-goal principal.
- **Rede (decisão do design):** Traefik entra na rede externa `stackpilot_net` e ganha `extra_hosts: host.docker.internal:host-gateway`. Rotas apontam para nomes de container nessa rede (padrão) ou para `host.docker.internal:<porta>` quando o destino é um serviço no host da WSL. As stacks gerenciadas devem entrar na `stackpilot_net` para serem alcançáveis.
- **Reinício após boot (decisão do design):** `restart: unless-stopped` + `systemctl enable docker`, de modo que o Traefik volta com o daemon. Não haverá unidade systemd separada para o Traefik.

### Configuração
- `.env` de produção nativo com paths absolutos da WSL e `SECRET_KEY` real.
- `.env.wsl.example` documentando os paths nativos; `.env.example` atual permanece como referência do deploy em container.

### Rede
- Windows → app: encaminhamento de localhost do WSL2 (`http://localhost:8000`).
- LAN → app/Traefik: `networkingMode=mirrored` (Windows 11) ou `netsh portproxy` para 8000/80/443. Documentar as duas opções.
- Autostart na inicialização do Windows: habilitar systemd e iniciar a distro/serviço via Tarefa Agendada chamando `wsl.exe`; o mecanismo exato fica a cargo do builder.

### Sem mudanças de código de aplicação
- O app já lê config por env e já cria diretórios ao salvar. Espera-se **nenhuma** alteração em `app/`, salvo se a verificação revelar necessidade (ex.: robustez do carregamento de `.env` sob systemd).

## 6. Testing / Verification
- Provisionamento: `docker run hello-world` funciona; `docker compose version` responde; `systemctl is-system-running` retorna `running`; `python3.14 --version` ok (ou `3.13` no fallback).
- `pytest` continua verde (nenhuma regressão de código).
- Manual:
  - `systemctl status stackpilot` ativo e reiniciando sozinho após falha.
  - `curl http://localhost:8000/login` responde 200.
  - Dashboard lista containers do Docker da WSL (via socket nativo).
  - Criar uma rota na UI grava em `TRAEFIK_DYNAMIC_DIR` e o Traefik (container) carrega o arquivo.
- Deploy em container existente continua funcionando com `docker compose up -d`.

## 7. Open / Left to Builder
- Nome da distro WSL, usuário de deploy e se será uma distro dedicada.
- Mecanismo exato de autostart no boot/logon do Windows.
- Se o deploy em container será mantido em paralelo ou marcado como legado.
- Expor apenas em localhost ou também na LAN.
- Detalhes do script de provisionamento (apt vs repositório oficial do Docker; como instalar Python 3.14 — deadsnakes/PPA, `uv`, ou pyenv — já que distros LTS costumam trazer versão menor).
- `certResolver: letsencrypt` já é referenciado nas rotas mas não existe config estática de resolver no Traefik atual — problema pré-existente, **fora** do escopo desta entrega.
