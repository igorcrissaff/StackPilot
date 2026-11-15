import json

import httpx
import pytest

from app.services.dockerhub_service import (
    DockerHubService,
    HubUnavailableError,
    InvalidImageReferenceError,
    split_reference,
)
from app.services.hub_cache import HubCache


def _service(handler, cache, ttl=3600):
    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://hub.docker.com"
    )
    return DockerHubService(
        cache=cache, ttl_seconds=ttl, api_base="https://hub.docker.com", timeout=5, client=client
    )


def test_split_reference():
    assert split_reference("nginx") == ("nginx", "latest")
    assert split_reference("jellyfin/jellyfin:10.9") == ("jellyfin/jellyfin", "10.9")
    with pytest.raises(InvalidImageReferenceError):
        split_reference("bad ref")


def test_search_parses_and_caches(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"results": [
            {"repo_name": "jellyfin/jellyfin", "short_description": "Media",
             "star_count": 10, "pull_count": 1000, "is_official": True}
        ]})

    svc = _service(handler, HubCache(tmp_path / "hub.db"))
    r1 = svc.search_images("jellyfin")
    svc.search_images("jellyfin")
    assert r1.images[0].repo_name == "jellyfin/jellyfin"
    assert r1.images[0].is_official is True
    assert r1.stale is False
    assert calls["n"] == 1


def test_search_serves_stale_on_429(tmp_path):
    cache = HubCache(tmp_path / "hub.db")
    cache.set_search("jellyfin", json.dumps([{"repo_name": "old/img", "pull_count": 1}]))
    svc = _service(lambda r: httpx.Response(429), cache, ttl=-1)
    r = svc.search_images("jellyfin")
    assert r.stale is True
    assert r.fetched_at is not None
    assert r.images[0].repo_name == "old/img"


def test_search_429_without_cache_raises(tmp_path):
    svc = _service(lambda r: httpx.Response(429), HubCache(tmp_path / "hub.db"))
    with pytest.raises(HubUnavailableError, match="Limite de requisi"):
        svc.search_images("nothing")


def test_list_tags_official_uses_library(tmp_path):
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        return httpx.Response(200, json={"results": [
            {"name": "latest", "last_updated": "2026-01-01T00:00:00Z"}
        ]})

    svc = _service(handler, HubCache(tmp_path / "hub.db"))
    r = svc.list_tags("nginx")
    assert seen["path"] == "/v2/repositories/library/nginx/tags/"
    assert r.tags[0].name == "latest"


def test_list_tags_rejects_registry_host(tmp_path):
    svc = _service(lambda r: httpx.Response(200, json={"results": []}), HubCache(tmp_path / "hub.db"))
    with pytest.raises(InvalidImageReferenceError):
        svc.list_tags("ghcr.io/org/app")
