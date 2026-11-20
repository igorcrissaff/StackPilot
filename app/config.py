from functools import lru_cache
from pathlib import Path
import platform
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    host_info: dict = {
        "hostname": platform.node(),
        "host_os": platform.system() + " " + platform.release(),
        "kernel_version": platform.version(),
    }

    stackpilot_user: str = "admin"
    stackpilot_password: str = "admin"
    secret_key: str = "change-me-in-production"
    stacks_dir: Path = Path("/opt/stacks")
    hub_db_path: Path = Path("/opt/stackpilot/stackpilot.db")
    metrics_db_path: Path = Path("/opt/stackpilot/metrics.db")
    hub_cache_ttl_seconds: int = 86400
    hub_api_base: str = "https://hub.docker.com"
    hub_request_timeout_seconds: float = 10.0
    compose_up_timeout_seconds: int = 600
    stackpilot_network: str = "stackpilot_net"


@lru_cache
def get_settings() -> Settings:
    return Settings()
