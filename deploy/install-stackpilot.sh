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

mkdir -p data/traefik/dynamic data/stacks

if [ ! -f .env ]; then
  sed "s#/opt/stackpilot#${APP_DIR}#g" .env.wsl.example > .env
  chmod 600 .env
fi

sed -e "s#__USER__#${SERVICE_USER}#g" -e "s#__APP_DIR__#${APP_DIR}#g" \
  deploy/stackpilot.service.template | sudo tee /etc/systemd/system/stackpilot.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now stackpilot.service

docker compose --env-file "$APP_DIR/.env" -f deploy/docker-compose.traefik.yml up -d

echo "StackPilot ativo. Veja: systemctl status stackpilot"
