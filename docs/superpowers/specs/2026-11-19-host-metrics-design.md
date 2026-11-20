# Métricas do host no dashboard

## Intenção e motivo

O StackPilot hoje mostra containers, stacks e imagens. O usuário quer visibilidade do servidor onde ele roda: utilização de recursos e qual sistema operacional está em uso, em um painel leve.

## Objetivos

- Exibir no dashboard métricas do **host** (StackPilot nativo no WSL/Linux):
  - CPU (percentual e número de núcleos)
  - Memória (usada/total/percentual) e swap
  - Disco raiz `/` (usado/total/percentual)
  - Load average (1/5/15 min quando disponível)
  - Uptime
  - Sistema operacional: distribuição/versão, kernel, arquitetura e hostname
- Atualização automática a cada **10 segundos** via HTMX, sem recarregar a página.
- Manter o padrão visual escuro e o uso mínimo de recursos.

## Não-objetivos

- Histórico/gráficos, alertas ou séries temporais.
- Métricas por container, GPU ou sensores.
- Suporte a métricas do host quando o StackPilot roda em container (modo nativo é o alvo).
- Depender de Prometheus/node_exporter.

## Restrições

- Python + FastAPI + Jinja2 + HTMX + Tailwind (CDN), sem Node.js.
- Nova dependência: `psutil` (cross-platform, leve).
- Deve funcionar em Linux/WSL e não quebrar no Windows (load average pode não existir).

## Abordagens consideradas

- **A) `psutil` + seção HTMX com polling de 10s** (escolhida): um `MetricsService` coleta os dados, um endpoint `GET /metrics` devolve uma partial, e o dashboard inclui a seção com polling HTMX. Simples, consistente e leve.
- **B) API JSON + render no navegador**: mais JS e flexibilidade para gráficos, mas não aproveita o HTMX existente.
- **C) Prometheus/node_exporter**: infra extra e mais pesada; descartada para um painel de homelab.

## Decisões de implementação

- `app/services/metrics_service.py` com modelo `SystemMetrics` (Pydantic) e `MetricsService.collect()`.
- Campos: `cpu_percent`, `cpu_count`, `load_1/5/15` (opcionais), `memory_used`, `memory_total`, `memory_percent`, `swap_used`, `swap_total`, `swap_percent`, `disk_used`, `disk_total`, `disk_percent`, `uptime_seconds`, `os_name`, `os_version`, `kernel`, `architecture`, `hostname`.
- SO: ler `/etc/os-release` (`PRETTY_NAME`/`NAME`+`VERSION`) com fallback para `platform.system()`/`platform.release()`; arquitetura via `platform.machine()`; hostname via `socket.gethostname()`.
- Disco medido em `/` via `psutil.disk_usage("/")`.
- CPU via `psutil.cpu_percent(interval=0.1)`; memória/swap via `psutil.virtual_memory()`/`swap_memory()`; uptime via `time.time() - psutil.boot_time()`.
- Endpoint `GET /metrics` (autenticado) em `app/routers/metrics.py`, retornando `partials/system_metrics.html`.
- Dashboard inclui a seção `partials/system_metrics.html` com `hx-get="/metrics"`, `hx-trigger="load, every 10s"` e `hx-swap="outerHTML"`.
- UI: cards com barras de progresso (CPU, memória, disco), dados de load/uptime e um card de SO.
- Testes: serviço com `psutil` mockado; endpoint autenticado e conteúdo renderizado; dashboard contendo a seção.

## O que fica com o implementador

- Layout exato dos cards dentro do padrão visual atual.
- Formatação de bytes/duração (ex.: GB, dias/horas).
- Escolha de exibir swap somente quando total > 0.
