from functools import lru_cache
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_base_domain(value: str) -> str:
    value = value.strip().lower().rstrip(".")
    if not value or "://" in value or "/" in value or any(ch.isspace() for ch in value):
        raise ValueError("BASE_DOMAIN must be a bare domain, e.g. home.arpa")
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    stackpilot_user: str = "admin"
    stackpilot_password: str = "admin"
    traefik_dynamic_dir: Path = Path("/etc/traefik/dynamic")
    secret_key: str = "change-me-in-production"
    stacks_dir: Path = Path("/opt/stacks")
    base_domain: str = "home.arpa"
    hub_db_path: Path = Path("/opt/stackpilot/stackpilot.db")
    hub_cache_ttl_seconds: int = 86400
    hub_api_base: str = "https://hub.docker.com"
    hub_request_timeout_seconds: float = 10.0
    compose_up_timeout_seconds: int = 600
    stackpilot_network: str = "stackpilot_net"

    @field_validator("base_domain")
    @classmethod
    def validate_base_domain(cls, v: str) -> str:
        return normalize_base_domain(v)


@lru_cache
def get_settings() -> Settings:
    return Settings()
