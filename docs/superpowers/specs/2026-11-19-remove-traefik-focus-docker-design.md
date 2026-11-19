# Remover Traefik e focar em containers e imagens

## Intenção e motivo

O StackPilot deixa de gerenciar roteamento HTTP com Traefik. O painel passa a ser focado 100% em gerenciamento de containers e imagens Docker, reduzindo superfície de código, configuração e deploy.

## Objetivos

- Remover toda a funcionalidade de rotas Traefik (UI, rotas HTTP, serviço, página de Configurações/base domain).
- Remover assets e variáveis de deploy do Traefik.
- Manter o gerenciamento de containers existente (listar, iniciar, parar, reiniciar, remover, logs, editar compose).
- Completar o gerenciamento de imagens: remover imagem e pull/atualizar tag, mantendo a busca no Docker Hub.
- Atualizar README, docs, `.env` de exemplo e testes; manter a suíte verde.

## Não-objetivos

- Implementar proxy/roteamento alternativo.
- Progresso em tempo real (streaming) do `docker pull`.
- Suporte a registry privado/autenticação.

## Restrições

- Frontend: FastAPI + Jinja2 + HTMX + Alpine.js + Tailwind (CDN), sem Node.js/npm.
- Confirmação obrigatória antes de remover imagem (modal Alpine).
- Manter o padrão visual atual (tema escuro estilo Portainer).

## Abordagens consideradas (imagens)

- **A) Ações inline com HTMX** — botões remover/atualizar e campo de pull na própria lista; erros inline. Simples e consistente. (escolhida)
- **B) Pull com progresso** — streaming/polling do output; mais complexo. (descartada)
- **C) Modal estilo Portainer** — puro modal/JS; mais código. (parcialmente adotada: modal apenas para confirmação)

Decisão final: ações inline via HTMX + modal de confirmação em Alpine.js.

## Decisões de implementação

### Remoções

- `app/routers/routes.py`, `app/services/traefik_service.py`.
- `app/routers/settings.py`, `app/services/settings_service.py`, `app/templates/settings.html`, `app/templates/partials/settings_general_form.html`.
- `app/templates/partials/route_list.html`, `app/templates/partials/route_edit_row.html`.
- `tests/test_traefik_service.py`, `tests/test_settings_service.py`, `tests/test_settings_router.py`.
- `deploy/docker-compose.traefik.yml`.
- Serviço `traefik`, volume `traefik_dynamic` e `depends_on` em `docker-compose.yml`.
- Variáveis `TRAEFIK_DYNAMIC_DIR` e `BASE_DOMAIN` dos `.env` de exemplo e scripts de deploy.
- Referências no README, `docs/deploy-wsl.md` e dashboard.

### Ajustes

- `app/config.py`: remover `traefik_dynamic_dir`, `base_domain`, `normalize_base_domain` e o validador; manter as demais configurações.
- `app/dependencies.py`: remover `get_traefik_service`, `get_effective_base_domain`, `get_settings_service`.
- `app/main.py`: remover routers/rotas/dependências de Traefik; dashboard passa a carregar somente containers (e contagem de imagens).
- `app/templates/dashboard.html`: remover seção e navegação de rotas e link de Configurações; trocar o card de rotas por métrica de imagens locais.
- Scripts `deploy/provision-wsl.sh` e `deploy/install-stackpilot.sh`: remover diretório dinâmico do Traefik e o `docker compose ... docker-compose.traefik.yml up -d`; manter criação da rede `stackpilot_net` (necessária para stacks).

### Novas ações de imagens

- `DockerService.remove_image(ref, force=False)` e `DockerService.pull_image(ref)`.
- Erros amigáveis: imagem não encontrada e imagem em uso.
- `app/routers/docker.py`: `POST /docker/images/remove` e `POST /docker/images/pull`, retornando `partials/image_list.html` com mensagem de sucesso/erro.
- `app/templates/partials/image_list.html`:
  - formulário de pull por referência;
  - botão "Remover" por tag (e por imagem sem tag) com modal Alpine de confirmação;
  - botão "Atualizar" por tag que faz pull daquela tag;
  - mensagens de sucesso/erro no topo.
- `app/templates/base.html`: incluir Alpine.js via CDN.

## Verificação

- `pytest` verde.
- Testes novos para `remove_image`/`pull_image` no `DockerService` e para os endpoints de imagens.
- Testes de deploy/config/rotas atualizados para refletir a ausência do Traefik.
