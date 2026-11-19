#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo ./deploy/provision-wsl.sh" >&2
  exit 1
fi

DEPLOY_USER="${STACKPILOT_USER:-${SUDO_USER:-root}}"
APP_DIR="${APP_DIR:-/opt/stackpilot}"
STACKS_DIR="${STACKS_DIR:-$APP_DIR/data/stacks}"
PY_VERSION="${PY_VERSION:-3.14}"

# 1. Enable systemd in WSL
if ! grep -q '^systemd=true' /etc/wsl.conf 2>/dev/null; then
  printf '\n[boot]\nsystemd=true\n' >> /etc/wsl.conf
fi
if [ "$(ps -p 1 -o comm= 2>/dev/null)" != "systemd" ]; then
  echo "systemd habilitado em /etc/wsl.conf."
  echo "No Windows, rode 'wsl --shutdown' e reabra a distro; depois rode este script de novo." >&2
  exit 1
fi

# 2. Base packages
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg

# 3. Docker Engine from the official repository
. /etc/os-release
install -m 0755 -d /etc/apt/keyrings
curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker

# 4. Docker group for the deploy user
groupadd -f docker
usermod -aG docker "$DEPLOY_USER"

# 5. uv (system-wide) and Python for the deploy user
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  install -m 0755 /root/.local/bin/uv /usr/local/bin/uv
fi
sudo -u "$DEPLOY_USER" -H /usr/local/bin/uv python install "$PY_VERSION"

# 6. Data directories and external network
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$STACKS_DIR"
docker network inspect stackpilot_net >/dev/null 2>&1 || docker network create stackpilot_net

echo "Host provisionado. Usuário '$DEPLOY_USER' precisa de novo login para o grupo docker."
