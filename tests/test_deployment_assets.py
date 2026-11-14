from pathlib import Path

import yaml

COMPOSE = Path("deploy/docker-compose.traefik.yml")


def _traefik() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_traefik_compose_service_and_restart():
    svc = _traefik()["services"]["traefik"]
    assert svc["image"].startswith("traefik:v3")
    assert svc["restart"] == "unless-stopped"
    assert "host.docker.internal:host-gateway" in svc["extra_hosts"]


def test_traefik_compose_external_network():
    net = _traefik()["networks"]["internal"]
    assert net["name"] == "stackpilot_net"
    assert net["external"] is True


def test_traefik_compose_binds_dynamic_dir_and_ports():
    traefik = _traefik()["services"]["traefik"]
    volumes = traefik["volumes"]
    assert any(v.endswith(":/etc/traefik/dynamic") for v in volumes)
    assert any("${TRAEFIK_DYNAMIC_DIR:" in v for v in volumes)
    for port in ("80:80", "443:443", "8080:8080"):
        assert port in traefik["ports"]


ENV_WSL = Path(".env.wsl.example")


def _env_map(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def test_env_wsl_example_has_required_keys_and_absolute_paths():
    env = _env_map(ENV_WSL)
    for key in (
        "STACKPILOT_USER",
        "STACKPILOT_PASSWORD",
        "SECRET_KEY",
        "TRAEFIK_DYNAMIC_DIR",
        "STACKS_DIR",
    ):
        assert key in env
    assert env["TRAEFIK_DYNAMIC_DIR"].startswith("/")
    assert env["STACKS_DIR"].startswith("/")


UNIT = Path("deploy/stackpilot.service.template")


def test_systemd_unit_template_directives():
    text = UNIT.read_text(encoding="utf-8")
    for needle in (
        "[Unit]",
        "[Service]",
        "[Install]",
        "User=__USER__",
        "WorkingDirectory=__APP_DIR__",
        "EnvironmentFile=__APP_DIR__/.env",
        "ExecStart=__APP_DIR__/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000",
        "Restart=on-failure",
        "After=network-online.target docker.service",
        "Wants=network-online.target docker.service",
        "WantedBy=multi-user.target",
    ):
        assert needle in text


def test_provision_script_has_required_logic():
    text = Path("deploy/provision-wsl.sh").read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert "systemd=true" in text
    assert "wsl --shutdown" in text
    assert "docker-ce" in text
    assert "docker-compose-plugin" in text
    assert "usermod -aG docker" in text
    assert "stackpilot_net" in text
    assert "uv python install" in text


def test_install_script_has_required_logic():
    text = Path("deploy/install-stackpilot.sh").read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert "uv venv" in text
    assert "uv pip install" in text
    assert ".env.wsl.example" in text
    assert "stackpilot.service.template" in text
    assert "systemctl enable --now stackpilot.service" in text
    assert "docker-compose.traefik.yml" in text


DOC = Path("docs/deploy-wsl.md")


def test_wsl_deploy_doc_covers_key_steps():
    text = DOC.read_text(encoding="utf-8")
    for needle in (
        "wsl --install -d Ubuntu",
        "provision-wsl.sh",
        "install-stackpilot.sh",
        "systemctl status stackpilot",
        "networkingMode=mirrored",
        "wsl --shutdown",
        "stackpilot_net",
    ):
        assert needle in text
