from app.config import Settings


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("STACKPILOT_PASSWORD", "secret123")
    settings = Settings()
    assert settings.stackpilot_user == "admin"
    assert settings.stackpilot_password == "secret123"


def test_settings_reads_paths_from_env(monkeypatch, tmp_path):
    stacks = tmp_path / "stacks"
    monkeypatch.setenv("STACKS_DIR", str(stacks))
    settings = Settings()
    assert settings.stacks_dir == stacks
    assert not hasattr(settings, "traefik_dynamic_dir")


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
