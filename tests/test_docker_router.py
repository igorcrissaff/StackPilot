from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.dependencies import get_docker_service, get_hub_cache
from app.main import app
from app.services.docker_service import ContainerInfo, ImageInfo
from app.services.hub_cache import UsedImage


def _client():
    c = TestClient(app)
    c.post("/login", data={"username": "admin", "password": "admin"})
    return c


def test_docker_page_renders_images_and_containers():
    mock_docker = MagicMock()
    mock_docker.list_images.return_value = [
        ImageInfo(id="sha256:abc", short_id="abc", tags=["nginx:alpine"], size=48, created="2026-01-01")
    ]
    mock_docker.list_containers.return_value = [
        ContainerInfo(id="c1", short_id="c1", name="web", image="nginx", status="running")
    ]
    mock_cache = MagicMock()
    mock_cache.list_used_images.return_value = [
        UsedImage(image="redis:7", last_used_at=1, use_count=1, stack_name="cache")
    ]
    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    app.dependency_overrides[get_hub_cache] = lambda: mock_cache
    try:
        r = _client().get("/docker")
        assert r.status_code == 200
        assert "Images" in r.text and "Containers" in r.text
        assert "nginx:alpine" in r.text
        assert "redis:7" in r.text
        assert "web" in r.text
    finally:
        app.dependency_overrides.clear()


def test_docker_page_renders_dangling_image():
    mock_docker = MagicMock()
    mock_docker.list_images.return_value = [
        ImageInfo(id="sha256:def", short_id="def", tags=[], size=50, created="2026-01-02")
    ]
    mock_docker.list_containers.return_value = []
    mock_cache = MagicMock()
    mock_cache.list_used_images.return_value = []
    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    app.dependency_overrides[get_hub_cache] = lambda: mock_cache
    try:
        r = _client().get("/docker")
        assert r.status_code == 200
        assert "sha256:def" in r.text
    finally:
        app.dependency_overrides.clear()


def test_docker_images_partial_renders_used_images():
    mock_docker = MagicMock()
    mock_docker.list_images.return_value = []
    mock_cache = MagicMock()
    mock_cache.list_used_images.return_value = [
        UsedImage(image="redis:7", last_used_at=1, use_count=1, stack_name="cache")
    ]
    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    app.dependency_overrides[get_hub_cache] = lambda: mock_cache
    try:
        r = _client().get("/docker/images")
        assert r.status_code == 200
        assert "redis:7" in r.text
    finally:
        app.dependency_overrides.clear()


def test_docker_page_requires_auth():
    client = TestClient(app)
    for path in ("/docker", "/docker/images"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"


from app.dependencies import get_dockerhub_service
from app.services.dockerhub_service import (
    HubImage,
    HubSearchResult,
    HubTag,
    HubTagsResult,
    HubUnavailableError,
)


def test_hub_search_renders_results():
    mock_hub = MagicMock()
    mock_hub.search_images.return_value = HubSearchResult(
        images=[HubImage(repo_name="jellyfin/jellyfin", pull_count=1000, is_official=True)]
    )
    app.dependency_overrides[get_dockerhub_service] = lambda: mock_hub
    try:
        r = _client().get("/hub/search?q=jellyfin")
        assert r.status_code == 200
        assert "jellyfin/jellyfin" in r.text
    finally:
        app.dependency_overrides.clear()


def test_hub_search_no_results():
    mock_hub = MagicMock()
    mock_hub.search_images.return_value = HubSearchResult(images=[])
    app.dependency_overrides[get_dockerhub_service] = lambda: mock_hub
    try:
        r = _client().get("/hub/search?q=zzzz")
        assert r.status_code == 200
        assert "Nenhuma imagem" in r.text
    finally:
        app.dependency_overrides.clear()


def test_hub_search_error_shows_message():
    mock_hub = MagicMock()
    mock_hub.search_images.side_effect = HubUnavailableError("limite de requisições")
    app.dependency_overrides[get_dockerhub_service] = lambda: mock_hub
    try:
        r = _client().get("/hub/search?q=jellyfin")
        assert r.status_code == 200
        assert "limite de requisições" in r.text
    finally:
        app.dependency_overrides.clear()


def test_hub_tags_renders():
    mock_hub = MagicMock()
    mock_hub.list_tags.return_value = HubTagsResult(
        repo="jellyfin/jellyfin", tags=[HubTag(name="latest")]
    )
    app.dependency_overrides[get_dockerhub_service] = lambda: mock_hub
    try:
        r = _client().get("/hub/tags?repo=jellyfin/jellyfin")
        assert r.status_code == 200
        assert "latest" in r.text
    finally:
        app.dependency_overrides.clear()

