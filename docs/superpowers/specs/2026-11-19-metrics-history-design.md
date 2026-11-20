# Métricas com histórico, intervalo configurável e exportação CSV

## Intenção e motivo

Evoluir a seção "Servidor": o usuário quer (1) escolher o intervalo de atualização pelo painel e (2) ver gráficos com o consumo recente, mantendo um registro de longo prazo para pesquisas futuras e exportação.

## Objetivos

- Intervalo de atualização configurável na interface, inteiro entre **5 e 900 segundos**, persistido.
- Gráfico recente de consumo com janela **variável de `10×` a `100×` o intervalo, passo de `10×`** (10, 20, …, 100), a partir de amostras cruas.
- Histórico de longo prazo: **média de cada período de 5 minutos**, guardado **indefinidamente** em SQLite.
- Coleta contínua em background (sem depender de alguém com o painel aberto).
- Exportação do histórico em **CSV**.
- Manter o padrão visual escuro e o uso de CDN (sem Node).

## Não-objetivos

- Tela de estatísticas/consultas sobre o histórico (fica para depois).
- Alertas, retenção/apagamento automático, múltiplos usuários.
- Métricas de containers, GPU ou sensores.
- Suporte a múltiplos workers (o projeto roda em processo único).

## Anti-objetivos

- Buracos no histórico quando ninguém acessa o painel.
- Guardar apenas médias de 5 min e perder a resolução usada pelo gráfico recente.
- Quebrar o comportamento atual do painel ou exigir infraestrutura externa.

## Restrições

- Python/FastAPI/Jinja2/HTMX/Tailwind/Alpine; sem Node.
- SQLite via `sqlite3` (padrão já usado em `HubCache`).
- Reaproveitar o fallback de caminho de banco (`_resolve_db_path`).
- Autenticação existente em todas as rotas novas.

## Abordagens consideradas

- **A) Coletor em background + SQLite + Chart.js via CDN** (escolhida): task asyncio amostra o host a cada 10s, buffer recente em memória, flush de médias de 5 min no SQLite; Chart.js desenha o gráfico.
- **B) Coleta sob demanda**: gera lacunas no histórico; descartada.
- **C) Prometheus/node_exporter**: infra pesada e fora do escopo do painel; descartada.

## Decisões de implementação

### Coleta

- Task asyncio iniciada no `lifespan` do FastAPI, amostrando a cada `min(10, intervalo_configurado)` segundos (o intervalo é relido a cada ciclo). O teto de 10s garante médias de 5 min confiáveis e evita lacunas; o piso de `intervalo` garante ao menos uma amostra por fatia do gráfico quando o intervalo é 5–9s. O intervalo configurado também controla a **atualização da UI** e o **tamanho das janelas**.
- `await asyncio.to_thread(...)` para a coleta bloquear o mínimo possível.
- Instância única guardada em `app.state`; encerrada no shutdown.

### Buffer recente (gráfico)

- `deque` em memória com amostras `(timestamp, cpu_percent, memory_percent, swap_percent, disk_percent)`.
- Poda para no máximo `100 × intervalo_atual` segundos.
- Janela do gráfico = `multiplier × intervalo` (multiplier ∈ {10,20,…,100}); as amostras do buffer são agregadas em `multiplier` pontos (média por fatia de `intervalo` segundos). Default: `multiplier=30`.
- O `multiplier` escolhido é preservado entre os polls: o poll inclui o `<select>` (`hx-include`) e o servidor re-renderiza a opção `selected`; ao recarregar a página inteira volta ao default `30`.
- Após reinício o gráfico começa vazio e vai preenchendo.

### Histórico de longo prazo (SQLite)

- Novo caminho `metrics_db_path` (default `/opt/stackpilot/metrics.db`), **em arquivo separado** do DB do Hub, com fallback para `data/metrics.db` (generalizar o helper de fallback atual, que fixa `stackpilot.db`).
- Tabela `metrics_history`:
  - `bucket_start INTEGER PRIMARY KEY` (epoch alinhado a 300s)
  - `cpu_percent REAL`, `memory_percent REAL`, `memory_used INTEGER`, `memory_total INTEGER`
  - `swap_percent REAL`, `swap_used INTEGER`, `swap_total INTEGER`
  - `disk_percent REAL`, `disk_used INTEGER`, `disk_total INTEGER`
  - `load_1 REAL`, `load_5 REAL`, `load_15 REAL`
  - `sample_count INTEGER NOT NULL`
- A cada amostra, acumula no bucket corrente; ao mudar de bucket, grava a média via `INSERT ... ON CONFLICT(bucket_start) DO UPDATE`. **O update faz média ponderada pelo `sample_count` existente**, para que um flush parcial antes de reiniciar e um novo flush no mesmo bucket não sobrescrevam o histórico. Flush best-effort no shutdown.
- Buckets sem amostra (intervalo > 5 min é irrelevante aqui, pois a coleta é fixa em 10s) não existem.

### Configuração

- Tabela `app_settings(key TEXT PRIMARY KEY, value TEXT)` no mesmo SQLite.
- Chave `metrics_refresh_interval_seconds`, default **10**, validada em `5..900`.
- Nova página `/settings` (a antiga seção de settings foi removida com o Traefik) com um card "Métricas": formulário do intervalo e botão de exportar CSV. Link "Configurações" no menu.
- `POST /settings/metrics` valida e salva; resposta HTMX com mensagem de sucesso/erro (ou redirect quando sem HTMX).
- O intervalo é lido do banco a cada request; um dashboard já aberto passa a usar o novo valor no próximo poll (a partial re-renderizada carrega o novo `hx-trigger`). Não há push em tempo real.

### Gráfico

- Chart.js via CDN carregado só onde há gráfico.
- `GET /metrics?multiplier=N` devolve a partial atual + um bloco `<script type="application/json" id="metrics-chart-data">` com labels e séries (CPU, memória, disco, swap).
- Seletor de janela `<select>` dentro da partial, com `hx-get="/metrics" hx-include="this" hx-target="#system-metrics" hx-swap="outerHTML"`; opções `10×…100×` rotuladas com a duração real.
- JS em `app/static/js/metrics_chart.js` (vanilla, sem inline) escuta `htmx:afterSwap`/`htmx:onLoad` e cria/atualiza o `Chart` existente em vez de recriar.
- Eixo Y 0–100%; swap só aparece se `swap_total > 0`. Load/uptime seguem nos cards.

### Exportação

- `GET /metrics/export.csv` (autenticado) → `StreamingResponse(text/csv)`, todas as linhas ordenadas por `bucket_start`.
- Filtros opcionais `start`/`end` (epoch ou ISO-8601) para uso futuro; sem filtros exporta tudo.
- Colunas: `bucket_start` (ISO UTC) + todos os campos do histórico.
- Nome do arquivo `stackpilot-metrics-YYYYMMDD.csv`.
- Botão "Exportar CSV" no card de configurações de métricas.

## Testes

- Repositório (SQLite temporário): criação de tabelas, UPSERT/média por bucket, listagem ordenada.
- Coletor: agregação por bucket, flush ao trocar de bucket, poda e janelamento do buffer (sem dormir de verdade).
- Settings: aceitar 5 e 900, rejeitar <5, >900 e não inteiro; persistência.
- Rotas: `/settings` e `POST /settings/metrics` autenticados; `/metrics?multiplier` com JSON do gráfico e validação do range; `/metrics/export.csv` com `content-type` e linhas corretas; auth obrigatório em todas.
- Suíte existente continua verde.

## O que fica com o implementador

- Layout exato do card de configurações e do seletor de janela.
- Formatação de durações/rótulos de tempo.
- Detalhes de acessibilidade e espaçamento no padrão visual atual.
- Estratégia de flush no shutdown (best-effort).
