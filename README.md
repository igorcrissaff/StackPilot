# StackPilot

Painel de controle leve para servidores domésticos (homelab) em Python, com foco em gerenciar containers Docker e roteamento com Traefik.

## Objetivos

- **Interface inspirada no Portainer**: layout moderno com sidebar de navegação escura, cards métricos de visão geral (containers running/stopped, stacks ativas, rotas HTTP), badges de status com pulso luminoso, barra de ações rápidas e filtro de pesquisa instantâneo.
- **Gerenciar containers Docker** localmente via socket (`/var/run/docker.sock`): listar, iniciar, parar, reiniciar, remover e ver logs.
- **Buscar imagens no Docker Hub e criar stacks pelo painel**: pesquisa de imagens, escolha de tag, geração de um `compose.yaml` inicial e implantação (`docker compose up -d`) direto da interface, com cache local em SQLite para reduzir chamadas à API do Docker Hub.
- **Página Docker estilo Docker Desktop** em `/docker`, com abas "Images" (imagens locais, imagens já usadas em stacks e busca no Hub) e "Containers".
- **Editar Docker Compose de cada container (estilo Dockge)**: visualizar e editar o arquivo `compose.yaml`/`docker-compose.yml` e variáveis `.env`, com validação de sintaxe YAML, geração automática a partir de containers existentes e ação de salvar e implantar (`docker compose up -d`).
- **Gerenciar rotas HTTP do Traefik** como subdomínios de `BASE_DOMAIN` via arquivos dinâmicos YAML (file provider), com validação automática de subdomínios e URLs e resolução local pelo arquivo `hosts`.
- **Tudo em Python**, sem Node.js/npm para o frontend, usando FastAPI + Jinja2 + HTMX + Tailwind (CDN).
- **Baixo consumo de recursos**, ideal para Raspberry Pi e mini PCs.
- **Autenticação simples** de único administrador via sessão cookie assinada.

## Arquitetura

```
app/
├── auth.py            # Verificação de credenciais e decorator de autenticação
├── config.py          # Configuração via variáveis de ambiente (pydantic-settings)
├── dependencies.py    # Injeção de dependências (DockerService, TraefikService, ComposeService)
├── main.py            # FastAPI app, rotas de login/logout/dashboard
├── routers/
│   ├── containers.py  # Rotas HTMX para containers, logs e edição de compose
│   ├── docker.py      # Página /docker, busca no Hub, tags e criação de stacks
│   └── routes.py      # Rotas HTMX para criar/deletar rotas Traefik
├── services/
│   ├── compose_service.py  # Gerenciamento, validação e deploy de compose/stacks (Dockge-style)
│   ├── docker_service.py   # Wrapper do docker-py com tratamento de erros
│   ├── dockerhub_service.py # Cliente da API do Docker Hub (busca e tags)
│   ├── hub_cache.py        # Cache SQLite de buscas/tags e imagens já usadas
│   └── traefik_service.py  # Geração e validação de YAML dinâmico do Traefik
└── templates/
    ├── base.html, login.html, dashboard.html, docker.html
    └── partials/
        ├── container_compose.html
        ├── container_list.html
        ├── container_logs.html
        ├── create_compose.html
        ├── create_result.html
        ├── hub_search.html
        ├── hub_tags.html
        ├── image_list.html
        └── route_list.html
```

## Instalação e Uso

### Requisitos
- Python 3.11+
- Docker e docker-compose (ou Docker Desktop)
- Traefik v3 (iniciado via docker-compose)

### Desenvolvimento local

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -e ".[dev]"
pytest
```

### Rodando com Docker

```bash
cp .env.example .env
docker compose up -d
```

Acesse `http://localhost:8000` e faça login com as credenciais de `.env`. O cache do Docker Hub e a lista de imagens usadas ficam em `./data/stackpilot.db` (volume montado em `/opt/stackpilot`).

### Rodando nativamente em WSL2

Veja [docs/deploy-wsl.md](docs/deploy-wsl.md) para rodar o StackPilot como processo nativo numa distro WSL2, com acesso direto ao Docker Engine.

## Configuração

Variáveis de ambiente (via `.env`):

| Variável              | Padrão        | Descrição                            |
|-----------------------|---------------|--------------------------------------|
| `STACKPILOT_USER`     | `admin`       | Usuário do painel                    |
| `STACKPILOT_PASSWORD` | `admin`       | Senha do painel                      |
| `SECRET_KEY`          | change-me     | Chave secreta para sessões           |
| `TRAEFIK_DYNAMIC_DIR` | /etc/traefik/dynamic | Diretorio de rotas dinâmicas |
| `STACKS_DIR`          | /opt/stacks   | Diretório base de stacks Compose     |
| `BASE_DOMAIN`         | `home.arpa`   | Domínio base das rotas HTTP locais (subdomínios via `hosts`) |
| `HUB_DB_PATH`         | /opt/stackpilot/stackpilot.db | Caminho do SQLite de cache do Docker Hub (fallback `./data/stackpilot.db`) |
| `HUB_CACHE_TTL_SECONDS` | `86400`     | Validade do cache de buscas/tags do Docker Hub |
| `COMPOSE_UP_TIMEOUT_SECONDS` | `600`  | Timeout do `docker compose up -d` ao criar stack |
| `STACKPILOT_NETWORK`  | `stackpilot_net` | Rede externa anexada ao compose inicial |

## Testes

```bash
pytest
```