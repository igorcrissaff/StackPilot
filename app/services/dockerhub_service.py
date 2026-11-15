from __future__ import annotations

import json
import re

import httpx
from pydantic import BaseModel

from app.services.hub_cache import HubCache


class HubUnavailableError(Exception):
    pass


class InvalidImageReferenceError(Exception):
    pass


class HubImage(BaseModel):
    repo_name: str
    short_description: str = ""
    star_count: int = 0
    pull_count: int = 0
    is_official: bool = False


class HubTag(BaseModel):
    name: str
    last_updated: str = ""


class HubSearchResult(BaseModel):
    images: list[HubImage]
    stale: bool = False
    fetched_at: int | None = None


class HubTagsResult(BaseModel):
    repo: str
    tags: list[HubTag]
    stale: bool = False
    fetched_at: int | None = None


REPO_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*$")
TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")

RATE_LIMIT_MESSAGE = "Limite de requisições do Docker Hub atingido. Tente novamente mais tarde."


def split_reference(ref: str) -> tuple[str, str]:
    ref = ref.strip()
    if not ref or "@" in ref:
        raise InvalidImageReferenceError(f"Referência de imagem inválida: {ref!r}")

    repo, tag = ref, "latest"
    colon = ref.rfind(":")
    if colon != -1 and "/" not in ref[colon:]:
        repo, tag = ref[:colon], ref[colon + 1 :]

    if not REPO_RE.match(repo) or not TAG_RE.match(tag):
        raise InvalidImageReferenceError(f"Referência de imagem inválida: {ref!r}")

    return repo, tag


def _parse_images(payload: str) -> list[HubImage]:
    return [
        HubImage(
            repo_name=str(item.get("repo_name", "")),
            short_description=str(item.get("short_description") or ""),
            star_count=int(item.get("star_count") or 0),
            pull_count=int(item.get("pull_count") or 0),
            is_official=bool(item.get("is_official")),
        )
        for item in json.loads(payload)
    ]


def _parse_tags(payload: str) -> list[HubTag]:
    return [
        HubTag(
            name=str(item.get("name", "")),
            last_updated=str(item.get("last_updated") or ""),
        )
        for item in json.loads(payload)
    ]


class DockerHubService:
    def __init__(
        self,
        cache: HubCache,
        ttl_seconds: int,
        api_base: str = "https://hub.docker.com",
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ):
        self.cache = cache
        self.ttl_seconds = ttl_seconds
        self.api_base = api_base
        self.timeout = timeout
        self.client = client or httpx.Client(base_url=api_base, timeout=timeout)

    def search_images(self, query: str) -> HubSearchResult:
        q = query.strip().lower()
        if not q:
            return HubSearchResult(images=[])

        payload, fetched_at, is_stale = self.cache.get_search(q, self.ttl_seconds)
        if payload is not None and not is_stale:
            return HubSearchResult(images=_parse_images(payload), stale=False, fetched_at=fetched_at)

        error = self._fetch(
            "/v2/search/repositories/",
            {"query": q, "page_size": 25},
            on_success=lambda results: self.cache.set_search(q, json.dumps(results)),
        )
        if error is not None:
            if payload is not None:
                return HubSearchResult(images=_parse_images(payload), stale=True, fetched_at=fetched_at)
            raise error

        stored = self.cache.get_search(q, self.ttl_seconds)
        return HubSearchResult(
            images=_parse_images(stored[0]) if stored[0] is not None else [],
            stale=False,
            fetched_at=stored[1],
        )

    def list_tags(self, repo: str) -> HubTagsResult:
        normalized, _ = split_reference(repo)
        first_segment = normalized.split("/")[0]
        if "." in first_segment or ":" in first_segment:
            raise InvalidImageReferenceError(f"Registry não suportado: {repo!r}")

        api_repo = normalized if "/" in normalized else f"library/{normalized}"
        payload, fetched_at, is_stale = self.cache.get_tags(api_repo, self.ttl_seconds)
        if payload is not None and not is_stale:
            return HubTagsResult(
                repo=normalized, tags=_parse_tags(payload), stale=False, fetched_at=fetched_at
            )

        error = self._fetch(
            f"/v2/repositories/{api_repo}/tags/",
            {"page_size": 25},
            on_success=lambda results: self.cache.set_tags(api_repo, json.dumps(results)),
        )
        if error is not None:
            if payload is not None:
                return HubTagsResult(
                    repo=normalized, tags=_parse_tags(payload), stale=True, fetched_at=fetched_at
                )
            raise error

        stored = self.cache.get_tags(api_repo, self.ttl_seconds)
        return HubTagsResult(
            repo=normalized,
            tags=_parse_tags(stored[0]) if stored[0] is not None else [],
            stale=False,
            fetched_at=stored[1],
        )

    def _fetch(self, path: str, params: dict, on_success) -> HubUnavailableError | None:
        try:
            response = self.client.get(path, params=params)
        except httpx.HTTPError as exc:
            return HubUnavailableError(f"Docker Hub indisponível: {exc}")

        if response.status_code == 200:
            results = response.json().get("results") or []
            on_success(results)
            return None
        if response.status_code == 429:
            return HubUnavailableError(RATE_LIMIT_MESSAGE)
        return HubUnavailableError(f"Docker Hub indisponível: HTTP {response.status_code}")
