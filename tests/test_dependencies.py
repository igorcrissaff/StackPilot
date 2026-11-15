from app.config import Settings
from app.dependencies import (
    get_effective_base_domain,
    get_traefik_service,
)
from app.services.settings_service import SettingsService


class _BrokenService:
    def get_base_domain(self, default):
        raise RuntimeError("db unavailable")


def test_effective_base_domain_uses_override(tmp_path, monkeypatch):
    svc = SettingsService(tmp_path / "s.db")
    svc.set_base_domain("lab.local")
    monkeypatch.setattr(
        "app.dependencies.get_settings",
        lambda: Settings(_env_file=None, base_domain="home.arpa"),
    )
    assert get_effective_base_domain(svc) == "lab.local"


def test_effective_base_domain_falls_back_to_env(tmp_path, monkeypatch):
    svc = SettingsService(tmp_path / "s.db")
    monkeypatch.setattr(
        "app.dependencies.get_settings",
        lambda: Settings(_env_file=None, base_domain="home.arpa"),
    )
    assert get_effective_base_domain(svc) == "home.arpa"


def test_effective_base_domain_falls_back_when_db_fails(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.get_settings",
        lambda: Settings(_env_file=None, base_domain="home.arpa"),
    )
    assert get_effective_base_domain(_BrokenService()) == "home.arpa"


def test_traefik_service_uses_effective_base_domain():
    svc = get_traefik_service(base_domain="lab.local")
    assert svc.base_domain == "lab.local"
