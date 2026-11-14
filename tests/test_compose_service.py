import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.services.compose_service import ComposeInfo, ComposeService
from app.services.docker_service import DockerService


def _make_container_mock(
    cid="abc123456789",
    name="my-nginx",
    labels=None,
    image="nginx:alpine",
    status="running",
    port_bindings=None,
    env=None,
    binds=None,
):
    c = MagicMock()
    c.id = cid
    c.short_id = cid[:12]
    c.name = name
    c.labels = labels if labels is not None else {}
    c.status = status
    c.image.tags = [image]

    c.attrs = {
        "Config": {
            "Image": image,
            "Env": env or ["FOO=bar"],
        },
        "HostConfig": {
            "RestartPolicy": {"Name": "unless-stopped"},
            "PortBindings": port_bindings or {"80/tcp": [{"HostIp": "", "HostPort": "8080"}]},
            "Binds": binds or ["/tmp/data:/data:rw"],
        },
        "NetworkSettings": {
            "Networks": {"web_net": {}},
        },
    }
    return c


def test_validate_compose_yaml_valid():
    svc = ComposeService(docker_service=MagicMock())
    valid_yaml = """
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
"""
    is_valid, err, data = svc.validate_compose_yaml(valid_yaml)
    assert is_valid is True
    assert err is None
    assert "web" in data["services"]


def test_validate_compose_yaml_invalid_syntax():
    svc = ComposeService(docker_service=MagicMock())
    bad_yaml = "services:\n  web:\n   ports: [80:80"
    is_valid, err, data = svc.validate_compose_yaml(bad_yaml)
    assert is_valid is False
    assert "Erro de sintaxe no YAML" in err
    assert data is None


def test_validate_compose_yaml_missing_services():
    svc = ComposeService(docker_service=MagicMock())
    bad_yaml = "version: '3.8'\nnetworks:\n  foo: {}"
    is_valid, err, _ = svc.validate_compose_yaml(bad_yaml)
    assert is_valid is False
    assert "services" in err


def test_get_compose_info_existing_file(tmp_path):
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services:\n  app:\n    image: app:v1\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET=12345\n", encoding="utf-8")

    mock_container = _make_container_mock(
        cid="cont123",
        name="myapp",
        labels={
            "com.docker.compose.project": "myproject",
            "com.docker.compose.service": "app",
            "com.docker.compose.project.config_files": str(compose_file),
            "com.docker.compose.project.working_dir": str(tmp_path),
        },
    )

    mock_docker_svc = MagicMock(spec=DockerService)
    mock_docker_svc.get_container.return_value = mock_container

    svc = ComposeService(docker_service=mock_docker_svc, stacks_dir=tmp_path)
    info = svc.get_compose_info("cont123")

    assert info.container_id == "cont123"
    assert info.stack_name == "myproject"
    assert info.service_name == "app"
    assert info.file_path == compose_file.resolve()
    assert "image: app:v1" in info.compose_content
    assert info.is_generated is False
    assert info.exists_on_disk is True
    assert info.env_content == "SECRET=12345\n"


def test_get_compose_info_generated_when_not_on_disk(tmp_path):
    mock_container = _make_container_mock(
        cid="standalone123",
        name="standalone-nginx",
        labels={},
        image="nginx:alpine",
    )

    mock_docker_svc = MagicMock(spec=DockerService)
    mock_docker_svc.get_container.return_value = mock_container

    svc = ComposeService(docker_service=mock_docker_svc, stacks_dir=tmp_path)
    info = svc.get_compose_info("standalone123")

    assert info.container_id == "standalone123"
    assert info.is_generated is True
    assert info.exists_on_disk is False
    assert "nginx:alpine" in info.compose_content
    assert "8080:80" in info.compose_content
    assert "FOO=bar" in info.compose_content


def test_save_compose_file(tmp_path):
    mock_container = _make_container_mock(
        cid="c1",
        name="test-cont",
        labels={"com.docker.compose.project": "stack_test"},
    )
    mock_docker_svc = MagicMock(spec=DockerService)
    mock_docker_svc.get_container.return_value = mock_container

    svc = ComposeService(docker_service=mock_docker_svc, stacks_dir=tmp_path)
    yaml_content = "services:\n  test:\n    image: redis:alpine\n"
    env_content = "REDIS_PORT=6379\n"

    target_path = tmp_path / "stack_test" / "compose.yaml"
    saved_path = svc.save_compose_file(
        "c1",
        compose_content=yaml_content,
        env_content=env_content,
        custom_path=target_path,
    )

    assert saved_path == target_path
    assert saved_path.exists()
    assert saved_path.read_text(encoding="utf-8") == yaml_content
    env_saved = target_path.parent / ".env"
    assert env_saved.exists()
    assert env_saved.read_text(encoding="utf-8") == env_content


def test_save_compose_file_invalid_yaml(tmp_path):
    svc = ComposeService(docker_service=MagicMock(), stacks_dir=tmp_path)
    with pytest.raises(ValueError, match="Erro de sintaxe"):
        svc.save_compose_file("c1", compose_content="invalid: yaml: [")


@patch("subprocess.run")
def test_deploy_compose_success(mock_subproc, tmp_path):
    mock_subproc.return_value = subprocess.CompletedProcess(
        args=["docker", "compose"],
        returncode=0,
        stdout="Container stack_test-web-1 Started",
        stderr="",
    )

    mock_container = _make_container_mock(
        cid="c2",
        name="web-cont",
        labels={"com.docker.compose.project": "webstack"},
    )
    mock_docker_svc = MagicMock(spec=DockerService)
    mock_docker_svc.get_container.return_value = mock_container

    svc = ComposeService(docker_service=mock_docker_svc, stacks_dir=tmp_path)
    yaml_content = "services:\n  web:\n    image: nginx:alpine\n"

    success, msg = svc.deploy_compose("c2", yaml_content)
    assert success is True
    assert "Started" in msg
    mock_subproc.assert_called_once()
