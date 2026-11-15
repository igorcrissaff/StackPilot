import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("STACKPILOT_PASSWORD", "secret123")
    settings = Settings()
    assert settings.stackpilot_user == "admin"
    assert settings.stackpilot_password == "secret123"


def test_settings_reads_paths_from_env(monkeypatch, tmp_path):
    dynamic = tmp_path / "traefik-dynamic"
    stacks = tmp_path / "stacks"
    monkeypatch.setenv("TRAEFIK_DYNAMIC_DIR", str(dynamic))
    monkeypatch.setenv("STACKS_DIR", str(stacks))
    settings = Settings()
    assert settings.traefik_dynamic_dir == dynamic
    assert settings.stacks_dir == stacks


def test_settings_base_domain_default(monkeypatch):
    monkeypatch.delenv("BASE_DOMAIN", raising=False)
    settings = Settings(_env_file=None)
    assert settings.base_domain == "home.arpa"


def test_settings_normalizes_base_domain(monkeypatch):
    monkeypatch.setenv("BASE_DOMAIN", " Lab.Local. ")
    settings = Settings(_env_file=None)
    assert settings.base_domain == "lab.local"


def test_settings_rejects_invalid_base_domain():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, base_domain="http://lab.local")


def test_settings_hub_defaults():
    s = Settings(_env_file=None)
    assert s.hub_cache_ttl_seconds == 86400
    assert s.hub_api_base == "https://hub.docker.com"
    assert s.hub_request_timeout_seconds == 10.0
    assert s.compose_up_timeout_seconds == 600
    assert s.stackpilot_network == "stackpilot_net"


def test_settings_hub_env_overrides(monkeypatch):
    monkeypatch.setenv("HUB_CACHE_TTL_SECONDS", "60")
    monkeypatch.setenv("STACKPILOT_NETWORK", "mynet")
    s = Settings(_env_file=None)
    assert s.hub_cache_ttl_seconds == 60
    assert s.stackpilot_network == "mynet"
