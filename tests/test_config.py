from app.config import Settings


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("STACKPILOT_PASSWORD", "secret123")
    settings = Settings()
    assert settings.stackpilot_user == "admin"
    assert settings.stackpilot_password == "secret123"
