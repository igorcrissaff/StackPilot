from functools import lru_cache
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    stackpilot_user: str = "admin"
    stackpilot_password: str = "admin"
    traefik_dynamic_dir: Path = Path("/etc/traefik/dynamic")
    secret_key: str = "change-me-in-production"
    stacks_dir: Path = Path("/opt/stacks")
    base_domain: str = "home.arpa"

    @field_validator("base_domain")
    @classmethod
    def validate_base_domain(cls, v: str) -> str:
        v = v.strip().lower().rstrip(".")
        if not v or "://" in v or "/" in v or any(ch.isspace() for ch in v):
            raise ValueError("BASE_DOMAIN must be a bare domain, e.g. home.arpa")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
