# Integração com Docker Hub: buscar imagens e criar containers pelo painel

Data: 2026-11-15
Status: aprovado

## Intenção

Permitir, dentro do StackPilot, buscar imagens públicas no Docker Hub, escolher
imagem e tag, gerar um `compose.yaml` inicial, editá-lo no painel e implantar o
novo container como stack em `STACKS_DIR`. A interface segue o Docker Desktop:
uma visão Docker dedicada com duas abas, **Images** (imagens locais/puxadas +
busca no Hub) e **Containers** (lista atual). Buscas, listas de tags e imagens
já usadas ficam em SQLite para reduzir chamadas à API do Hub e contornar o rate
limit.

## Objetivos

- Nova visão Docker (estilo Docker Desktop) com abas **Images** e **Containers**.
- Buscar imagens públicas no Hub por nome, mostrando nome, descrição, se é
  oficial, estrelas e pulls.
- Listar tags de uma imagem e escolher a tag desejada.
- A partir de uma imagem (do Hub ou local), gerar um compose inicial e abrir o
  editor de compose; o usuário edita e implanta.
- Cache em SQLite de buscas e tags, com TTL; em `429`/erro de rede, servir o
  cache antigo (stale) quando existir.
- Registro de "imagens já utilizadas" em SQLite, exibido na aba Images para
  reuso rápido, sem passar pela busca.
- Reaproveitar `ComposeService` e `docker compose up` para criar a stack.

## Não-objetivos

- Login/autenticação no Docker Hub, imagens privadas ou organizações pagas.
- Proxy/mirror de registry ou pull por registry próprio.
- Deletar ou gerenciar imagens locais (além de listar) nesta versão.
- Push de imagens, build de imagens, Dockerfile.
- Atualizar/recriar imagens já implantadas; fica para um ciclo futuro.
- Múltiplos hosts/endpoints por painel.

## Anti-objetivos

- Guardar credenciais no banco (não há auth no Hub nesta versão).
- Quebrar o fluxo atual de listar/operar containers e editar compose de
  containers existentes.
- Travar o painel quando o Hub estiver fora ou limitado: mostrar o erro e usar
  cache quando possível.
- Confiar em texto vindo do Hub para montar comandos de shell; usar sempre
  `subprocess` com lista de argumentos e validar referências de imagem.

## Restrições

- Python 3.11+, FastAPI + Jinja2 + HTMX + Tailwind (CDN); sem Node no runtime.
- Baixo consumo (Raspberry Pi/mini PC): SQLite local, sem servidor extra.
- Acesso ao Docker via docker-py e ao compose via `docker compose` (subprocess),
  como hoje.
- API pública do Docker Hub sem auth: sujeita a rate limit e a mudanças; sem SLA.
- `STACKS_DIR` continua sendo a base das stacks; escrita do compose segue o
  padrão existente.

## Abordagens consideradas

1. **Fonte da busca**: API pública do Hub (escolhida) vs CLI `docker search` vs
   registry v2. O CLI bate no mesmo rate limit, devolve menos dados e não lista
   tags; o registry exige auth para busca. A API do Hub entrega metadados e tags.
2. **Cache**: SQLite (escolhida) vs arquivos JSON vs sem cache. SQLite dá TTL,
   consulta e histórico num arquivo só; JSON vira lógica manual; sem cache ignora
   o requisito de contornar o rate limit.
3. **UI**: visão Docker dedicada estilo Docker Desktop com abas Images/Containers
   (escolhida, opção B) vs abas dentro do painel atual (opção A) vs modal de
   criação. A dedicada é a mais fiel ao Docker Desktop e foi a escolhida na
   conversa.
4. **Criação**: gerar compose e reusar o editor + `docker compose up` (escolhida)
   vs `docker run` direto via docker-py. Compose preserva o modelo do projeto e
   permite editar antes de subir.

## Decisões

### Dependências

- Adicionar `httpx` às dependências de runtime em `pyproject.toml` (já está em
  `dev`). Usar `sqlite3` da biblioteca padrão; sem ORM.

### Configuração (`app/config.py`)

- `hub_db_path: Path` (default `/opt/stackpilot/stackpilot.db`), com fallback
  local `./data/stackpilot.db` quando `/opt` não for gravável — análogo ao
  fallback de `ComposeService._resolve_stacks_dir`.
- `hub_cache_ttl_seconds: int = 86400` (24h) para buscas e tags.
- `hub_api_base: str = "https://hub.docker.com"`.
- `hub_request_timeout_seconds: float = 10.0`.
- `compose_up_timeout_seconds: int = 600` (o primeiro pull de uma imagem grande
  pode passar dos 120s atuais).
- `stackpilot_network: str = "stackpilot_net"` (rede externa das stacks
  gerenciadas pelo painel).
- `docker-compose.yml` ganha o volume `./data:/opt/stackpilot` para o SQLite
  sobreviver à recriação do container; `data/` entra no `.gitignore`.
- `.env.example` e `.env.wsl.example` documentam as novas variáveis.

### Banco e cache (`app/services/hub_cache.py`)

- `init_db(path)` idempotente cria as tabelas:
  - `search_cache(query TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at INTEGER NOT NULL)`
  - `tag_cache(repo TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at INTEGER NOT NULL)`
  - `used_images(image TEXT PRIMARY KEY, last_used_at INTEGER NOT NULL, use_count INTEGER NOT NULL, stack_name TEXT)`
- Conexão por operação, `PRAGMA journal_mode=WAL`, `row_factory` por nome.
- `get_cached_search(query, ttl) -> (payload | None, stale: bool)` e
  `set_cached_search(query, payload)`; análogos para tags.
- `record_used_image(image, stack_name)` (upsert, incrementa `use_count`) e
  `list_used_images(limit)` ordenado por `last_used_at` desc.

### Serviço do Hub (`app/services/dockerhub_service.py`)

- `DockerHubService(cache, ttl, api_base, timeout)` com:
  - `search_images(query) -> HubSearchResult`: normaliza a query; cache válido
    retorna sem rede; senão chama `/v2/search/repositories/` e grava cache; em
    `429`/erro de rede, retorna cache antigo marcado `stale` (se houver) ou
    levanta `HubUnavailableError`.
  - `list_tags(repo) -> HubTagsResult`: valida a referência; usa namespace
    `library` para imagens oficiais; mesma política de cache/stale.
- Normalização de referência: aceitar `nginx`, `jellyfin/jellyfin`,
  `ns/repo:tag`; separar `repo` e `tag`.
- Modelos pydantic: `HubImage`, `HubTag`, `HubSearchResult`, `HubTagsResult`
  (com `stale: bool` e `fetched_at`).

### Imagens locais e criação

- `DockerService.list_images()` via docker-py (`client.images.list()`),
  retornando `ImageInfo(id, short_id, tags, size, created)`; erro vira
  `DockerUnavailableError`.
- Cada tag de uma imagem local é uma linha selecionável, preservando a
  referência completa (`nginx:alpine`, `ghcr.io/org/app:1.2`, `lscr.io/...`).
  Imagens sem tag (dangling) aparecem como `<none>` e podem ser usadas pelo id
  da imagem (`image: <id>`), com aviso.
- `ComposeService.create_stack(stack_name, compose_content, env_content)`:
  valida o YAML (reusa `validate_compose_yaml`), sanitiza `stack_name` (slug
  `[a-z0-9-_]`), **recusa** se `STACKS_DIR/<stack>` já existir (erro claro, sem
  sobrescrever), escreve `compose.yaml` e `.env` e roda `docker compose up -d`,
  extraindo a lógica atual de `deploy_compose` para `_run_compose_up(file_path)`.
- `generate_starter_compose(repo, tag)` gera o serviço sem `container_name` (o
  Compose deriva `<stack>-<servico>-1`, evitando colisão ao criar mais de um
  container da mesma imagem). Nome do serviço derivado do último segmento do
  repo (slug), ou do `stack_name`.
- O compose inicial anexa a rede externa `stackpilot_network` (default
  `stackpilot_net`), para que a nova stack seja alcançável pelo Traefik e por
  outras stacks; a seção `networks` marca a rede como `external: true`.
- Deploy é síncrono, com `compose_up_timeout_seconds` (default 600s) para
  acomodar o primeiro pull; a UI mostra o estado de envio durante a requisição.
- O `docker compose up` baixa a imagem se ela não existir localmente.
- Só registra em `used_images` (todas as imagens `image:` do compose implantado)
  quando o deploy tem sucesso.

### Rotas (`app/routers/hub.py` e/ou `docker.py`)

- `GET /docker` → página dedicada (aba default Images) usando `base.html`.
- `GET /docker/images` → partial da aba Images: form de busca + imagens locais +
  imagens já usadas (subseções com HTMX).
- `GET /hub/search?q=` → partial com resultados do Hub (selo de cache/stale).
- `GET /hub/tags?repo=` → partial com as tags da imagem.
- `GET /hub/compose?repo=&tag=` → partial do editor de compose preenchido com o
  compose inicial + campo do nome da stack.
- `POST /docker/create` → recebe `stack_name`, `compose_content`, `env_content`,
  chama `create_stack`; em sucesso registra `used_images` e devolve partial com
  mensagem/saída; em falha devolve erro preservando o compose.
- A aba Containers reaproveita `GET /containers` e as ações existentes.
- Todas as rotas novas usam `Depends(require_auth)`.

### Templates

- `app/templates/docker.html`: layout estilo Docker Desktop — header com abas
  Images/Containers, coluna esquerda (lista) e painel direito
  (detalhe/editor de compose), no tema escuro atual.
- Partials: `hub_search.html`, `hub_tags.html`, `image_list.html` (locais +
  usadas), `create_compose.html` (editor) e `create_result.html`.
- `dashboard.html`: link "Docker" na sidebar levando a `/docker`; o dashboard
  continua como visão geral (métricas e rotas).
- A aba Containers inclui `partials/container_list.html` e os painéis de
  compose/logs existentes.

### Erros e rate limit

- `HubUnavailableError` com mensagem clara (rede, `429`, timeout).
- Quando `429` e houver cache (mesmo expirado), servir com selo "cache — pode
  estar desatualizado".
- Timeout curto para não travar a UI; requisições HTMX mostram o erro no painel.

### Segurança

- Validar `repo`/`tag` com regex de referência Docker (sem espaços/metacaracteres).
- Sanitizar `stack_name` e confinar `file_path` a `STACKS_DIR` (resolver e
  checar prefixo), evitando path traversal.
- Nenhum segredo no banco; sem credenciais do Hub.
- Sempre `subprocess.run([...])` com argumentos em lista.

## O que fica a cargo de quem implementa

- Caminho default do banco e fallback (análogo a `_resolve_stacks_dir`).
- Detalhes visuais da visão Docker (espaçamento, cores dentro do tema atual).
- Limite/paginação de resultados (proposta: 25 por busca, 25 tags; tags ordenadas
  por `last_updated` desc).
- Se a lista de "usadas" mostra também a stack de origem e o contador.
- Textos de ajuda e mensagens de erro em português.
- Como a visão Docker se integra à navegação (link na sidebar vs rota raiz).
- Rótulo visual para imagens dangling e para o selo de cache/stale.

## Verificação

- `pytest`:
  - `DockerHubService`: parse/normalização de referências, cache hit/miss e
    expiração, stale em `429` (httpx mockado), timeout.
  - `HubCache`: init idempotente, get/set, TTL, `used_images` incrementa e lista.
  - `ComposeService.create_stack`: valida, confina ao `STACKS_DIR`, recusa stack
    existente, compose inicial inclui a rede externa, deploy mockado
    (subprocess), registra usadas só no sucesso.
  - Routers: `/docker`, `/hub/search`, `/hub/tags`, `/hub/compose` e
    `/docker/create` com dependências mockadas e auth.
  - `DockerService.list_images` com client mockado.
- Manual: buscar "jellyfin" → escolher tag → editar compose → criar → container
  aparece na aba Containers; repetir a busca não chama o Hub de novo (cache); a
  imagem aparece em "usadas".
