from unittest.mock import MagicMock
import pytest
from docker.errors import DockerException, NotFound

from app.services.docker_service import (
    ContainerNotFoundError,
    DockerService,
    DockerUnavailableError,
    ImageInfo,
)


def _make_mock_container(cid="abc123def456", name="nginx", image="nginx:latest", status="running"):
    c = MagicMock()
    c.short_id = cid[:12]
    c.id = cid
    c.name = name
    c.image.tags = [image]
    c.status = status
    c.logs.return_value = b"log line 1\nlog line 2\n"
    return c


def test_list_containers():
    client = MagicMock()
    client.containers.list.return_value = [_make_mock_container()]
    svc = DockerService(client=client)

    containers = svc.list_containers()
    assert len(containers) == 1
    assert containers[0].id == "abc123def456"
    assert containers[0].name == "nginx"
    assert containers[0].image == "nginx:latest"
    assert containers[0].status == "running"


def test_list_containers_docker_unavailable():
    client = MagicMock()
    client.containers.list.side_effect = DockerException("socket missing")
    svc = DockerService(client=client)

    with pytest.raises(DockerUnavailableError):
        svc.list_containers()


def test_container_action_start_stop_restart_remove():
    client = MagicMock()
    container = _make_mock_container()
    client.containers.get.return_value = container
    svc = DockerService(client=client)

    svc.container_action("abc123def456", "start")
    container.start.assert_called_once()

    svc.container_action("abc123def456", "stop")
    container.stop.assert_called_once()

    svc.container_action("abc123def456", "restart")
    container.restart.assert_called_once()

    svc.container_action("abc123def456", "remove")
    container.remove.assert_called_once_with(force=True)


def test_container_action_not_found():
    client = MagicMock()
    client.containers.get.side_effect = NotFound("no such container")
    svc = DockerService(client=client)

    with pytest.raises(ContainerNotFoundError):
        svc.container_action("missing", "start")


def test_get_logs():
    client = MagicMock()
    container = _make_mock_container()
    client.containers.get.return_value = container
    svc = DockerService(client=client)

    logs = svc.get_logs("abc123def456", tail=50)
    assert "log line 1" in logs
    container.logs.assert_called_once_with(tail=50)


def test_list_images():
    client = MagicMock()
    tagged = MagicMock()
    tagged.id = 'sha256:abc'
    tagged.short_id = 'abc'
    tagged.tags = ['nginx:alpine']
    tagged.attrs = {'Size': 123, 'Created': '2026-01-01T00:00:00Z'}
    dangling = MagicMock()
    dangling.id = 'sha256:def'
    dangling.short_id = 'def'
    dangling.tags = []
    dangling.attrs = {'Size': 50, 'Created': '2026-01-02T00:00:00Z'}
    client.images.list.return_value = [tagged, dangling]

    images = DockerService(client=client).list_images()
    assert images[0].tags == ['nginx:alpine']
    assert images[0].size == 123
    assert images[1].tags == []


def test_list_images_unavailable():
    client = MagicMock()
    client.images.list.side_effect = DockerException('socket missing')
    with pytest.raises(DockerUnavailableError):
        DockerService(client=client).list_images()

