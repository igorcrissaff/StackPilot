# Configurações Gerais: hostname base editável, com estrutura extensível

Data: 2026-11-15
Status: aguardando aprovação

## Intenção

Dar ao StackPilot uma área de Configurações Gerais onde o administrador altera o
hostname base (hoje `BASE_DOMAIN`, vindo do `.env`) direto pelo painel, sem
editar arquivos nem reiniciar o serviço. Nesta versão só o hostname base é
editável, mas o armazenamento, o serviço e a tela nascem preparados para receber
idioma e tema (claro/escuro) como próximas chaves de configuração, inclusive
com separação entre configurações globais e por usuário.

## Objetivos

- Página `/settings` ("Configurações Gerais") com seção **Geral** contendo o
  campo de hostname base.
- Persistir as configurações em SQLite, no mesmo banco já usado pelo cache
  (`HUB_DB_PATH`), com fallback para o valor do `.env`.
- Aplicar o hostname efetivo imediatamente em todo lugar que hoje usa
  `base_domain`: rotas Traefik, dashboard e listagem de rotas.
- Ao trocar o hostname, regravar as regras `Host(...)` das rotas já existentes
  no arquivo gerenciado pelo StackPilot, para que não sumam nem quebrem.
- Deixar a estrutura pronta para futuras chaves (idioma/tema) e para
  configurações por usuário, sem precisar refatorar armazenamento nem UI.
- Botão para restaurar o valor padrão do `.env` (remove o override do banco).

## Não-objetivos

- Implementar tradução da interface (idioma) nesta versão.
- Implementar tema claro nesta versão (o tema escuro continua fixo).
- Tela de configurações por usuário (a coluna de escopo existe, mas a UI é global).
- Escrever de volta no `.env` ou exigir restart para aplicar.
- Editar outros parâmetros de ambiente (credenciais, paths, timeouts).

## Anti-objetivos

- Quebrar ou esconder rotas existentes ao mudar o hostname.
- Perder a configuração ao reiniciar o processo.
- Fazer o painel depender do banco para funcionar (falha do DB deve cair no
  valor do `.env`, não derrubar a página).

## Restrições

- Manter o stack atual: FastAPI + Jinja2 + HTMX + Tailwind via CDN, sem build
  step de frontend.
- Seguir o padrão visual das telas existentes (sidebar, cards, cores atuais).
- Admin único; autenticação por sessão (`require_auth`) em todas as rotas novas.

## Abordagens consideradas

1. **SQLite no banco existente (escolhida).** Tabela `app_settings` no mesmo DB
   do cache, com `SettingsService` lendo defaults do `.env` e aplicando overrides
   do banco. Escrita atômica, base pronta para escopo por usuário.
2. **Arquivo JSON (`data/settings.json`).** Modelo pydantic com escrita atômica.
   Simples e editável à mão, mas adiciona outro caminho para configurar/deployar
   e exige tratamento manual de concorrência.
3. **Escrever de volta no `.env`.** Rejeitada: frágil, não aplica em runtime sem
   restart e pode corromper comentários/formatação.

## Design

### Armazenamento

Nova tabela, criada na inicialização do serviço:

```sql
CREATE TABLE IF NOT EXISTS app_settings (
    scope TEXT NOT NULL,
    key   TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (scope, key)
);
```

- `scope` `global` para o hostname (hoje o único). Futuro: `user:<username>`
  para idioma/tema por usuário.
- `key` `base_domain` nesta versão.
- Mesmo caminho do banco do cache (`HUB_DB_PATH`), reaproveitando a resolução de
  caminho e o fallback `data/stackpilot.db` já existentes em `dependencies.py`.

### SettingsService

Novo `app/services/settings_service.py`:

- `init_db()` cria a tabela se não existir.
- `get(scope, key) -> str | None`, `set(scope, key, value)`,
  `delete(scope, key)`, `all(scope) -> dict[str, str]`.
- `get_base_domain(default: str) -> str`: devolve o override global, se houver,
  senão o default do `.env`.

Validação do hostname é compartilhada com `Settings`: extrair a normalização
(trim, lowercase, sem ponto final, sem esquema/barra/espaço) para um helper
reutilizado pelo `Settings` e pelo `SettingsService`.

### Injeção e uso do hostname efetivo

- `get_settings_service()` em `app/dependencies.py`, com o mesmo DB do cache.
- `get_traefik_service()` passa a usar `get_base_domain(settings.base_domain)`.
- `app/routers/routes.py` e o dashboard em `app/main.py` passam a usar o hostname
  efetivo em vez de `get_settings().base_domain`.
- Como o `TraefikService` é construído por request, a mudança vale na próxima
  requisição, sem restart.

### Migração das rotas ao trocar o hostname

Novo método em `TraefikService`, ex.: `rewrite_base_domain(old: str, new: str)`,
que no arquivo `stackpilot-routes.yml` percorre os routers cuja `rule` seja
`Host(...)` terminada no sufixo `.old` e regrava como `.new`, mantendo subdomínio,
serviço e entrypoints; routers fora do domínio antigo ficam intocados.

Fluxo do `POST /settings`:

1. Validar o novo hostname (mesma regra do `Settings`).
2. Se igual ao atual, salvar mesmo assim (idempotente) e retornar sucesso.
3. Persistir o override no banco.
4. Rodar `rewrite_base_domain(old, new)`; se falhar, remover o override recém-
   gravado (voltar ao antigo) e exibir erro, para não deixar rotas e
   configuração inconsistentes.

### Interface

- Novo router `app/routers/settings.py`, prefixo `/settings`, autenticado.
- `GET /settings` renderiza `settings.html` (estende `base.html`, mesmo layout
  de sidebar/topbar).
- `POST /settings` (HTMX) salva e devolve o partial do formulário com mensagem
  de sucesso ou erro.
- `POST /settings/reset` remove o override e volta ao valor do `.env`.
- Tela organizada em seções/cards: **Geral** (hostname base) agora; o espaço para
  **Aparência** (tema) e **Idioma** já fica previsto no layout, sem campos ainda.
- O card mostra o valor efetivo atual e indica se é padrão do `.env` ou override
  salvo no painel.
- Link "Configurações" na sidebar (desktop e drawer mobile) e/ou ícone de engrenagem
  no topo, nas telas `dashboard.html` e `docker.html`.

### Extensibilidade

- Armazenamento genérico por `(scope, key)` permite adicionar `language` e
  `theme` sem migração de schema.
- `scope` já distingue global de por usuário para quando idioma/tema virarem
  preferência de cada um.
- Página em seções: cada novo grupo vira um card/partial próprio.
- Validação por chave concentrada no `SettingsService`, não espalhada na UI.

## Testes

- `SettingsService`: cria tabela; `get`/`set`/`delete`/`all`; fallback para o
  default quando não há override; validação rejeita hostname inválido.
- `GET /settings` exige autenticação e renderiza o formulário com o valor atual.
- `POST /settings` válido persiste e devolve sucesso; inválido devolve erro sem
  gravar; `reset` remove o override.
- `get_traefik_service` usa o override do banco; sem override usa `.env`.
- `rewrite_base_domain` regrava rotas do domínio antigo e preserva as de fora.

## Deixado ao construtor

- Detalhes visuais exatos (espaçamento, cores, wording das mensagens).
- Como exibir a origem do valor (badge "padrão"/"personalizado").
- Se o link de Configurações fica só na sidebar ou também como ícone no topo.
