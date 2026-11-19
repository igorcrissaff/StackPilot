#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  echo "Run as the deploy user (not root)." >&2
  exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${APP_DIR:-$REPO_DIR}"
PY_VERSION="${PY_VERSION:-3.14}"
SERVICE_USER="$(id -un)"

cd "$APP_DIR"
command -v uv >/dev/null 2>&1 || { echo "uv not found; run deploy/provision-wsl.sh first." >&2; exit 1; }

uv python install "$PY_VERSION"
uv venv --python "$PY_VERSION" .venv
uv pip install --python .venv/bin/python -e ".[dev]"

if [ -f .env ]; then
  if ! grep -q "^STACKS_DIR=${APP_DIR}/" .env; then
    backup=".env.bak.$(date +%s)"
    echo "Aviso: .env existente não aponta para paths em ${APP_DIR}; backup em ${backup}." >&2
    mv .env "$backup"
  fi
fi

if [ ! -f .env ]; then
  sed "s#/opt/stackpilot#${APP_DIR}#g" .env.wsl.example > .env
  chmod 600 .env
fi

STACKS_DIR_VALUE="$(grep -E '^STACKS_DIR=' .env | cut -d= -f2-)"
mkdir -p "$STACKS_DIR_VALUE"

if grep -q '^STACKPILOT_PASSWORD=admin$' .env || grep -q '^SECRET_KEY=change-me-in-production$' .env; then
  echo "AVISO: credenciais ou SECRET_KEY padrão em .env. Edite antes de expor na LAN e reinicie o serviço." >&2
fi

sed -e "s#__USER__#${SERVICE_USER}#g" -e "s#__APP_DIR__#${APP_DIR}#g" \
  deploy/stackpilot.service.template | sudo tee /etc/systemd/system/stackpilot.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now stackpilot.service

echo "StackPilot ativo. Veja: systemctl status stackpilot"
