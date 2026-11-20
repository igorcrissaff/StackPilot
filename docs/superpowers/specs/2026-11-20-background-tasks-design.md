# Lista de Tarefas em Segundo Plano

**Data:** 2026-11-20

## Objetivo
Permitir que o usuário dispare ações longas (pull de imagem, compose up/down, criação e remoção de containers/imagens) sem travar a interface, acompanhando o andamento e o status de cada tarefa em uma página dedicada (`/tasks`).

## Não-objetivos
- Não exibir logs detalhados ou barra de progresso percentual por tarefa — apenas a tarefa (descrição/título) e seu status.
- Não incluir rotinas internas do sistema (como o coletor de métricas).
- Não adicionar indicador global/flutuante em outras páginas neste momento.

## Abordagem Escolhida
**Persistência em SQLite (`stackpilot.db`) + `asyncio.create_task` + polling HTMX**

- **Alternativa descartada:** Gerenciador apenas em memória (mais simples, porém perde o histórico ao reiniciar o servidor).
- **Trade-off aceito:** A tabela no SQLite preserva o histórico entre reinícios, exigindo marcação de tarefas que estavam `running` como `failed` (interrompidas) na inicialização da aplicação.

## Arquitetura e Componentes

1. **Modelo & Persistência (`app/services/task_service.py`)**
   - Tabela `tasks` no `stackpilot.db` (mesmo padrão de `hub_cache.py` / `metrics_settings.py`):
     - `id` (TEXT PK / UUID)
     - `title` (TEXT — ex.: `"Pull da imagem nginx:latest"`)
     - `status` (TEXT — `"running"`, `"completed"`, `"failed"`)
     - `created_at` (TEXT ISO-8601)
     - `finished_at` (TEXT ISO-8601, nullable)
   - `TaskService`:
     - `init_db()` / `mark_interrupted_tasks()`: na inicialização, marca tarefas `running` remanescentes como `failed`.
     - `enqueue(title, coro_fn)`: cria o registro `running` no SQLite, agenda `asyncio.create_task` para executar `coro_fn`, e ao finalizar atualiza o status para `completed` ou `failed` com `finished_at`.
     - `list_tasks(limit=50)`: retorna as tarefas ordenadas por `created_at DESC`.

2. **Integração com Ações Longas**
   - Converter ações demoradas nos routers (`docker.py`, `containers.py`) para usarem `TaskService.enqueue(...)`, retornando resposta imediata (feedback HTMX ou redirecionamento/aviso de que a tarefa foi iniciada em segundo plano).

3. **Router & Página Dedicada (`app/routers/tasks.py`)**
   - `GET /tasks`: renderiza `app/templates/tasks.html` (linkado na navegação em `base.html`).
   - `GET /tasks/list`: partial HTMX (`app/templates/partials/task_list.html`) com polling automático (`hx-trigger="every 2s"` quando houver tarefas `running`, ou polling contínuo simples) exibindo apenas o título da tarefa e seu status (badge).

4. **Testes**
   - Testes unitários para `TaskService` (criação, transição `running` -> `completed`/`failed`, `mark_interrupted_tasks`).
   - Testes de rota para `/tasks` e `/tasks/list`.
