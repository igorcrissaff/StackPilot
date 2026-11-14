# Deploy nativo em WSL2

Roda o StackPilot como processo Python nativo numa distro WSL2, com acesso direto ao Docker Engine da mesma distro. Instalação limpa: rotas e stacks antigas não são migradas.

## Pré-requisitos
- Windows 11 + WSL2.
- Uma distro **Ubuntu ou Debian** (não use a distro `docker-desktop`, que não tem shell completo).
- Acesso `sudo` na distro e o repositório clonado (ex.: `/opt/stackpilot`).

## 0. Garantir uma distro Ubuntu/Debian
Se `wsl -l -v` mostrar apenas `docker-desktop`, instale uma distro:
```
wsl --install -d Ubuntu
```
Depois abra a distro e clone o projeto:
```bash
sudo mkdir -p /opt/stackpilot
sudo chown "$USER:$USER" /opt/stackpilot
git clone <repo-url> /opt/stackpilot
cd /opt/stackpilot
```

## 1. Provisionar o host
```bash
sudo ./deploy/provision-wsl.sh
```
Na primeira execução o script habilita `systemd` em `/etc/wsl.conf` e para. No Windows:
```
wsl --shutdown
```
Reabra a distro e rode o script de novo. Ele instala `docker-ce` + plugin `docker compose`, adiciona seu usuário ao grupo `docker`, instala `uv` + Python 3.14 (fallback 3.13 com `PY_VERSION=3.13`), cria os diretórios de dados e a rede `stackpilot_net`.

> Saia e entre na distro após o script para o grupo `docker` valer.

## 2. Instalar o StackPilot
```bash
./deploy/install-stackpilot.sh
```
Cria `.venv` com Python 3.14, instala as dependências, gera `.env` a partir de `.env.wsl.example`, registra e ativa o serviço `systemd` e sobe o Traefik.

## 3. Acessar
- App: `http://localhost:8000` (login de `.env`).
- Traefik dashboard: `http://localhost:8080`.

## 4. Rede para a LAN
Por padrão o WSL2 fica atrás de NAT. Em Windows 11, crie `%USERPROFILE%\.wslconfig`:
```ini
[wsl2]
networkingMode=mirrored
```
Rode `wsl --shutdown` e reabra. Alternativa sem mirrored networking: `netsh interface portproxy` para 8000/80/443.

## 5. Iniciar no boot/login do Windows
Crie uma Tarefa Agendada no logon executando:
```
wsl.exe -d <distro> -u root -e systemctl start stackpilot.service
```
O Traefik volta sozinho pelo `restart: unless-stopped` com o `docker.service` habilitado.

## 6. Operação
```bash
systemctl status stackpilot
journalctl -u stackpilot -f
```

## 7. Traefik e rotas
O Traefik entra na rede externa `stackpilot_net`. Rotas apontam para nomes de containers dessa rede; para um serviço no host da WSL, use `http://host.docker.internal:<porta>`. As stacks gerenciadas precisam entrar na `stackpilot_net`.

## Manter o deploy em Docker
O caminho antigo continua válido:
```bash
cp .env.example .env
docker compose up -d
```
