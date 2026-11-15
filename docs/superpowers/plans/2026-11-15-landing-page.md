# StackPilot Landing Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar uma landing page estática para o StackPilot em `docs/pages/index.html` usando HTML, Tailwind CSS (CDN) e HTMX (CDN), pronta para hospedagem no GitHub Pages.

**Architecture:** Página única estática em `docs/pages/index.html` sem build step, mantendo separação dos arquivos `.md` em `docs/`. Opcionalmente, um workflow simples do GitHub Actions pode publicar `docs/pages/` no GitHub Pages.

**Tech Stack:** HTML5, Tailwind CSS (CDN), HTMX (CDN), GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-11-15-landing-page-design.md`

## Global Constraints

- Sem build step, sem Node.js/npm e sem frameworks JS pesados.
- Tudo contido em `docs/pages/` para não misturar com os `.md` de `docs/`.
- Tema escuro moderno alinhado ao painel StackPilot (inspirado em Portainer/Dockge).

## Review Focus

- Links quebrados para o repositório GitHub ou documentação `.md`.
- Responsividade em telas mobile e desktop.
- Carregamento correto dos CDNs (Tailwind e HTMX) sem erros de console.

---

### Task 1: Criar `docs/pages/index.html`

**Files:**
- Create: `docs/pages/index.html`

- [ ] **Step 1: Criar `docs/pages/index.html` com a estrutura completa da landing page**
  - Navbar com logo/nome StackPilot e links (Recursos, Arquitetura, Quick Start, GitHub).
  - Hero section com proposta de valor para homelabs e gestores de TI, badges de status e CTAs (Ver no GitHub / Guia Rápido).
  - Seção de Recursos (4 cards: Containers Docker, Docker Hub & Stacks, Editor Compose estilo Dockge, Rotas Traefik).
  - Seção de Arquitetura & Stack Leve (Python, FastAPI, Jinja2, HTMX, Tailwind, SQLite — ideal para Raspberry Pi / mini PCs).
  - Seção Quick Start com abas/trechos para Docker Compose e WSL2.
  - Rodapé com créditos de portfólio e links para `README.md` e `docs/deploy-wsl.md`.

- [ ] **Step 2: Verificar o HTML**
  - Abrir ou validar a sintaxe básica e confirmar que todos os links e classes Tailwind estão corretos.

### Task 2: Configurar workflow opcional de deploy no GitHub Pages

**Files:**
- Create: `.github/workflows/pages.yml`

- [ ] **Step 1: Criar `.github/workflows/pages.yml` para publicar `docs/pages/` no GitHub Pages**
  - Trigger em `push` na branch `main` (quando `docs/pages/**` mudar) e `workflow_dispatch`.
  - Usar `actions/upload-pages-artifact` apontando para `docs/pages` e `actions/deploy-pages`.

- [ ] **Step 2: Verificar YAML do workflow**
  - Conferir indentação e permissões (`pages: write`, `id-token: write`).
