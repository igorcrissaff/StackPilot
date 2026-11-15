# Design: StackPilot Landing Page

## Intent & Why
Criar uma landing page estática para o **StackPilot** que apresente o projeto para entusiastas de homelab e gestores de TI, funcionando também como peça de portfólio e porta de entrada para a documentação.

## Goals
- Página única responsiva em `docs/pages/index.html` usando **HTML + Tailwind CSS (CDN) + HTMX (CDN)** (sem build step ou Node.js).
- Seções claras: Hero com proposta de valor e CTAs (GitHub / Quick Start), Principais Recursos (Containers, Docker Hub & Stacks, Editor Compose, Rotas Traefik), Arquitetura leve (Python/FastAPI/SQLite), Guia rápido de instalação (Docker e WSL2) e Rodapé com links de portfólio/repositório.
- Visual alinhado ao próprio StackPilot (tema escuro moderno, inspirado em Portainer/Dockge, com badges de status).

## Non-Goals / Anti-Goals
- Sem backend dinâmico, sem build tools (`npm`, `vite`, `webpack`) e sem frameworks JS pesados.
- Não duplicar toda a documentação técnica; linkar para os `.md` do repositório quando necessário.

## Constraints & Approaches
- **Abordagem escolhida:** Arquivo estático em `docs/pages/index.html` separado dos `.md` em `docs/`.
- **Trade-off:** O GitHub Pages nativo só serve `/` ou `/docs` diretamente; para servir `docs/pages/` na raiz do Pages, pode-se usar um workflow simples do GitHub Actions (opcional) ou acessar via `/pages/`.
- **Alternativa descartada:** Colocar `index.html` direto em `docs/` (misturaria com os `.md` de documentação).
