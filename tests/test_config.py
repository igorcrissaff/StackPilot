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
