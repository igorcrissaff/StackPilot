from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.dependencies import get_docker_service, get_hub_cache
from app.main import app
from app.services.docker_service import ContainerInfo, ImageInUseError, ImageInfo, ImagePullError
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


from app.dependencies import get_compose_service


def test_compose_editor_prefills():
    mock_compose = MagicMock()
    mock_compose.generate_starter_compose.return_value = "services:\n  jellyfin:\n    image: jellyfin/jellyfin:latest\n"
    mock_compose.derive_service_name.return_value = "jellyfin"
    app.dependency_overrides[get_compose_service] = lambda: mock_compose
    try:
        r = _client().get("/docker/compose?image=jellyfin/jellyfin:latest")
        assert r.status_code == 200
        assert "image: jellyfin/jellyfin:latest" in r.text
        assert 'value="jellyfin"' in r.text
    finally:
        app.dependency_overrides.clear()


def test_create_success_records_used_images():
    mock_compose = MagicMock()
    mock_compose.create_stack.return_value = (True, "Stack criada")
    mock_compose.extract_images.return_value = ["jellyfin/jellyfin:latest"]
    mock_cache = MagicMock()
    app.dependency_overrides[get_compose_service] = lambda: mock_compose
    app.dependency_overrides[get_hub_cache] = lambda: mock_cache
    try:
        r = _client().post(
            "/docker/create",
            data={"stack_name": "jellyfin", "image": "jellyfin/jellyfin:latest",
                  "compose_content": "services:\n  jellyfin:\n    image: jellyfin/jellyfin:latest\n",
                  "env_content": ""},
        )
        assert r.status_code == 200
        assert "Stack criada" in r.text
        mock_cache.record_used_image.assert_called_once_with("jellyfin/jellyfin:latest", "jellyfin")
    finally:
        app.dependency_overrides.clear()


def test_create_failure_preserves_compose():
    mock_compose = MagicMock()
    mock_compose.create_stack.return_value = (False, "falha no deploy")
    app.dependency_overrides[get_compose_service] = lambda: mock_compose
    app.dependency_overrides[get_hub_cache] = lambda: MagicMock()
    try:
        r = _client().post(
            "/docker/create",
            data={"stack_name": "jellyfin", "image": "jellyfin/jellyfin:latest",
                  "compose_content": "services:\n  jellyfin:\n    image: jellyfin/jellyfin:latest\n",
                  "env_content": ""},
        )
        assert r.status_code == 200
        assert "falha no deploy" in r.text
        assert "image: jellyfin/jellyfin:latest" in r.text
    finally:
        app.dependency_overrides.clear()


def _image_override(mock_docker):
    mock_cache = MagicMock()
    mock_cache.list_used_images.return_value = []
    mock_docker.list_images.return_value = []
    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    app.dependency_overrides[get_hub_cache] = lambda: mock_cache


def test_remove_image_endpoint_refreshes_list():
    mock_docker = MagicMock()
    _image_override(mock_docker)
    try:
        r = _client().post("/docker/images/remove", data={"image": "nginx:alpine"})
        assert r.status_code == 200
        mock_docker.remove_image.assert_called_once_with("nginx:alpine", force=False)
        assert "removida" in r.text.lower()
    finally:
        app.dependency_overrides.clear()


def test_remove_image_in_use_shows_error():
    mock_docker = MagicMock()
    mock_docker.remove_image.side_effect = ImageInUseError("em uso por container")
    _image_override(mock_docker)
    try:
        r = _client().post("/docker/images/remove", data={"image": "nginx:alpine"})
        assert r.status_code == 200
        assert "em uso por container" in r.text
    finally:
        app.dependency_overrides.clear()


def test_pull_image_endpoint_refreshes_list():
    mock_docker = MagicMock()
    _image_override(mock_docker)
    try:
        r = _client().post("/docker/images/pull", data={"image": "nginx:alpine"})
        assert r.status_code == 200
        mock_docker.pull_image.assert_called_once_with("nginx:alpine")
        assert "baixada" in r.text.lower()
    finally:
        app.dependency_overrides.clear()


def test_pull_image_error_shows_message():
    mock_docker = MagicMock()
    mock_docker.pull_image.side_effect = ImagePullError("falha ao baixar")
    _image_override(mock_docker)
    try:
        r = _client().post("/docker/images/pull", data={"image": "bad/image"})
        assert r.status_code == 200
        assert "falha ao baixar" in r.text
    finally:
        app.dependency_overrides.clear()
