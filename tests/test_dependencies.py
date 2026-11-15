from app.config import Settings
from app.dependencies import (
    get_effective_base_domain,
    get_traefik_service,
)
from app.services.settings_service import SettingsService


def _raise_runtime(*args, **kwargs):
    raise RuntimeError("db unavailable")


def test_effective_base_domain_uses_override(tmp_path, monkeypatch):
    svc = SettingsService(tmp_path / "s.db")
    svc.set_base_domain("lab.local")
    monkeypatch.setattr(
        "app.dependencies.get_settings",
        lambda: Settings(_env_file=None, base_domain="home.arpa"),
    )
    monkeypatch.setattr("app.dependencies.get_settings_service", lambda: svc)
    assert get_effective_base_domain() == "lab.local"


def test_effective_base_domain_falls_back_to_env(tmp_path, monkeypatch):
    svc = SettingsService(tmp_path / "s.db")
    monkeypatch.setattr(
        "app.dependencies.get_settings",
        lambda: Settings(_env_file=None, base_domain="home.arpa"),
    )
    monkeypatch.setattr("app.dependencies.get_settings_service", lambda: svc)
    assert get_effective_base_domain() == "home.arpa"


def test_effective_base_domain_falls_back_when_service_fails(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.get_settings",
        lambda: Settings(_env_file=None, base_domain="home.arpa"),
    )
    monkeypatch.setattr(
        "app.dependencies.get_settings_service", _raise_runtime
    )
    assert get_effective_base_domain() == "home.arpa"


def test_traefik_service_uses_effective_base_domain():
    svc = get_traefik_service(base_domain="lab.local")
    assert svc.base_domain == "lab.local"
