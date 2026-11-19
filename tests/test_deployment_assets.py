from pathlib import Path

import yaml

ENV_WSL = Path(".env.wsl.example")
UNIT = Path("deploy/stackpilot.service.template")
DOC = Path("docs/deploy-wsl.md")
PROVISION = Path("deploy/provision-wsl.sh")
INSTALL = Path("deploy/install-stackpilot.sh")
ROOT_COMPOSE = Path("docker-compose.yml")


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
    for key in ("STACKPILOT_USER", "STACKPILOT_PASSWORD", "SECRET_KEY", "STACKS_DIR"):
        assert key in env
    assert "TRAEFIK_DYNAMIC_DIR" not in env
    assert "BASE_DOMAIN" not in env
    assert env["STACKS_DIR"].startswith("/")


def test_env_examples_define_docker_hub_defaults():
    for path in (Path(".env.example"), ENV_WSL):
        env = _env_map(path)
        assert env["HUB_CACHE_TTL_SECONDS"] == "86400"
        assert env["COMPOSE_UP_TIMEOUT_SECONDS"] == "600"
        assert env["STACKPILOT_NETWORK"] == "stackpilot_net"
        assert "HUB_DB_PATH" in env


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


def test_systemd_unit_renders_without_placeholders():
    rendered = (
        UNIT.read_text(encoding="utf-8")
        .replace("__USER__", "deploy")
        .replace("__APP_DIR__", "/opt/stackpilot")
    )
    assert "__" not in rendered
    assert "ExecStart=/opt/stackpilot/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000" in rendered
    assert "EnvironmentFile=/opt/stackpilot/.env" in rendered


def test_provision_script_has_required_logic():
    text = PROVISION.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert "systemd=true" in text
    assert "wsl --shutdown" in text
    assert "docker-ce" in text
    assert "docker-compose-plugin" in text
    assert "usermod -aG docker" in text
    assert "stackpilot_net" in text
    assert "uv python install" in text
    assert "TRAEFIK_DYNAMIC_DIR" not in text


def test_install_script_has_required_logic():
    text = INSTALL.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert "uv venv" in text
    assert "uv pip install" in text
    assert ".env.wsl.example" in text
    assert "stackpilot.service.template" in text
    assert "systemctl enable --now stackpilot.service" in text
    assert "docker-compose.traefik.yml" not in text
    assert "TRAEFIK_DYNAMIC_DIR" not in text


def test_install_script_validates_existing_env():
    text = INSTALL.read_text(encoding="utf-8")
    assert ".env.bak" in text
    assert 'mkdir -p "$STACKS_DIR_VALUE"' in text


def test_install_script_warns_on_default_secrets():
    text = INSTALL.read_text(encoding="utf-8")
    assert "credenciais" in text
    assert "SECRET_KEY" in text


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


def test_wsl_deploy_doc_security_and_fallback():
    text = DOC.read_text(encoding="utf-8")
    for needle in (
        "PY_VERSION=3.13 ./deploy/install-stackpilot.sh",
        "SECRET_KEY",
        "systemctl restart stackpilot",
    ):
        assert needle in text


def test_docs_and_readme_have_no_traefik_references():
    readme = Path("README.md").read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")
    for text in (readme, doc):
        assert "Traefik" not in text
        assert "TRAEFIK_DYNAMIC_DIR" not in text
        assert "BASE_DOMAIN" not in text


def test_readme_focuses_on_containers_and_images():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "Docker Hub" in text
    assert "images" in text.lower() or "imagens" in text.lower()


def test_root_compose_has_no_traefik():
    data = yaml.safe_load(ROOT_COMPOSE.read_text(encoding="utf-8"))
    assert "traefik" not in data["services"]
    assert "./data:/opt/stackpilot" in data["services"]["stackpilot"]["volumes"]

def test_no_traefik_references_in_app_landing_and_packaging():
    paths = [
        *Path("app/templates").rglob("*.html"),
        Path("docs/pages/index.html"),
        Path("pyproject.toml"),
        Path("README.md"),
    ]
    offenders = [str(p) for p in paths if "Traefik" in p.read_text(encoding="utf-8")]
    assert offenders == []
