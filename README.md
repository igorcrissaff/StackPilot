# StackPilot

Painel de controle leve para servidores domésticos (homelab) em Python, com foco em gerenciar containers Docker e roteamento com Traefik.

## Objetivos

- **Gerenciar containers Docker** localmente via socket (`/var/run/docker.sock`): listar, iniciar, parar, reiniciar, remover e ver logs.
- **Gerenciar rotas HTTP/HTTPS do Traefik** via arquivos dinâmicos YAML (file provider), com validação automática de domínios e URLs antes de escrever.
- **Tudo em Python**, sem Node.js/npm para o frontend, usando FastAPI + Jinja2 + HTMX + Tailwind (CDN).
- **Baixo consumo de recursos**, ideal para Raspberry Pi e mini PCs.
- **Autenticação simples** de único administrador via sessão cookie assinada.

## Arquitetura

```
app/
├── auth.py            # Verificação de credenciais e decorator de autenticação
├── config.py          # Configuração via variáveis de ambiente (pydantic-settings)
├── dependencies.py    # Injeção de dependências (DockerService, TraefikService)
├── main.py            # FastAPI app, rotas de login/logout/dashboard
├── routers/
│   ├── containers.py  # Rotas HTMX para containers e logs
│   └── routes.py      # Rotas HTMX para criar/deletar rotas Traefik
├── services/
│   ├── docker_service.py   # Wrapper do docker-py com tratamento de erros
│   └── traefik_service.py  # Geração e validação de YAML dinâmico do Traefik
└── templates/
    ├── base.html, login.html, dashboard.html
    └── partials/
        ├── container_list.html
        ├── container_logs.html
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

Acesse `http://localhost:8000` e faça login com as credenciais de `.env`.

## Configuração

Variáveis de ambiente (via `.env`):

| Variável              | Padrão        | Descrição                            |
|-----------------------|---------------|--------------------------------------|
| `STACKPILOT_USER`     | `admin`       | Usuário do painel                    |
| `STACKPILOT_PASSWORD` | `admin`       | Senha do painel                      |
| `SECRET_KEY`          | change-me     | Chave secreta para sessões           |
| `TRAEFIK_DYNAMIC_DIR` | /etc/traefik/dynamic | Diretorio de rotas dinâmicas |

## Testes

```bash
pytest
```