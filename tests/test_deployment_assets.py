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
