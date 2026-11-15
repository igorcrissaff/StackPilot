from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import (
    get_docker_service,
    get_settings_service,
    get_traefik_service,
)
from app.main import app
from app.services.settings_service import SettingsService
from app.services.traefik_service import RouteConfig, TraefikService


def _authed_client():
    client = TestClient(app)
    client.post("/login", data={"username": "admin", "password": "admin"})
    return client


def _override(monkeypatch, settings_svc, traefik_svc, base_domain="home.arpa"):
    monkeypatch.setattr(
        "app.routers.settings.get_settings",
        lambda: Settings(_env_file=None, base_domain=base_domain),
    )
    app.dependency_overrides[get_settings_service] = lambda: settings_svc
    app.dependency_overrides[get_traefik_service] = lambda: traefik_svc


def test_settings_requires_auth():
    resp = TestClient(app).get("/settings", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_settings_page_renders_current_value(monkeypatch):
    settings_svc = MagicMock()
    settings_svc.get_base_domain.return_value = "home.arpa"
    settings_svc.get.return_value = None
    traefik_svc = MagicMock()
    _override(monkeypatch, settings_svc, traefik_svc)
    try:
        resp = _authed_client().get("/settings")
        assert resp.status_code == 200
        assert 'name="base_domain"' in resp.text
        assert 'value="home.arpa"' in resp.text
        assert "Restaurar padrão" in resp.text
    finally:
        app.dependency_overrides.clear()


def test_post_settings_persists_and_migrates(monkeypatch):
    settings_svc = MagicMock()
    settings_svc.get_base_domain.return_value = "home.arpa"
    settings_svc.get.return_value = None
    settings_svc.set_base_domain.return_value = "lab.local"
    traefik_svc = MagicMock()
    _override(monkeypatch, settings_svc, traefik_svc)
    try:
        resp = _authed_client().post("/settings", data={"base_domain": " Lab.Local. "})
        assert resp.status_code == 200
        assert "Configurações salvas" in resp.text
        settings_svc.set_base_domain.assert_called_once_with(" Lab.Local. ")
        traefik_svc.rewrite_base_domain.assert_called_once_with("home.arpa", "lab.local")
    finally:
        app.dependency_overrides.clear()


def test_post_settings_invalid_shows_error(monkeypatch):
    settings_svc = MagicMock()
    settings_svc.get_base_domain.return_value = "home.arpa"
    settings_svc.get.return_value = None
    settings_svc.set_base_domain.side_effect = ValueError("bad")
    traefik_svc = MagicMock()
    _override(monkeypatch, settings_svc, traefik_svc)
    try:
        resp = _authed_client().post("/settings", data={"base_domain": "http://bad"})
        assert resp.status_code == 200
        assert "Hostname inválido" in resp.text
        traefik_svc.rewrite_base_domain.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_post_settings_migration_failure_reverts(monkeypatch):
    settings_svc = MagicMock()
    settings_svc.get_base_domain.return_value = "home.arpa"
    settings_svc.get.return_value = None
    settings_svc.set_base_domain.return_value = "lab.local"
    traefik_svc = MagicMock()
    traefik_svc.rewrite_base_domain.side_effect = OSError("disk full")
    _override(monkeypatch, settings_svc, traefik_svc)
    try:
        resp = _authed_client().post("/settings", data={"base_domain": "lab.local"})
        assert resp.status_code == 200
        assert "não foi possível atualizar as rotas" in resp.text.lower()
        settings_svc.reset_base_domain.assert_called_once()
    finally:
        app.dependency_overrides.clear()


def test_reset_settings_restores_default(monkeypatch):
    settings_svc = MagicMock()
    settings_svc.get_base_domain.return_value = "lab.local"
    settings_svc.get.return_value = "lab.local"
    traefik_svc = MagicMock()
    _override(monkeypatch, settings_svc, traefik_svc)
    try:
        resp = _authed_client().post("/settings/reset")
        assert resp.status_code == 200
        assert "Padrão do ambiente restaurado" in resp.text
        settings_svc.reset_base_domain.assert_called_once()
        traefik_svc.rewrite_base_domain.assert_called_once_with("lab.local", "home.arpa")
    finally:
        app.dependency_overrides.clear()


def test_settings_post_requires_auth():
    resp = TestClient(app).post(
        "/settings", data={"base_domain": "lab.local"}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_settings_reset_requires_auth():
    resp = TestClient(app).post("/settings/reset", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_settings_page_survives_store_failure(monkeypatch):
    settings_svc = MagicMock()
    settings_svc.get_base_domain.side_effect = RuntimeError("db unavailable")
    settings_svc.get.side_effect = RuntimeError("db unavailable")
    traefik_svc = MagicMock()
    _override(monkeypatch, settings_svc, traefik_svc)
    try:
        resp = _authed_client().get("/settings")
        assert resp.status_code == 200
        assert 'value="home.arpa"' in resp.text
        assert "Não foi possível ler as configurações" in resp.text
    finally:
        app.dependency_overrides.clear()


def test_dashboard_survives_settings_db_construction_failure(monkeypatch, tmp_path):
    mock_docker = MagicMock()
    mock_docker.list_containers.return_value = []
    mock_traefik = MagicMock()
    mock_traefik.list_routes.return_value = []
    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    app.dependency_overrides[get_traefik_service] = lambda: mock_traefik
    monkeypatch.setattr(
        "app.dependencies.get_settings",
        lambda: Settings(
            _env_file=None, base_domain="home.arpa", hub_db_path=tmp_path
        ),
    )
    try:
        resp = _authed_client().get("/")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_post_settings_same_domain_does_not_rewrite(monkeypatch, tmp_path):
    settings_svc = SettingsService(tmp_path / "s.db")
    traefik_svc = MagicMock()
    _override(monkeypatch, settings_svc, traefik_svc)
    try:
        resp = _authed_client().post("/settings", data={"base_domain": "home.arpa"})
        assert resp.status_code == 200
        assert "Configurações salvas" in resp.text
        traefik_svc.rewrite_base_domain.assert_not_called()
        assert settings_svc.get_base_domain("home.arpa") == "home.arpa"
    finally:
        app.dependency_overrides.clear()


def test_migration_failure_restores_previous_override(monkeypatch, tmp_path):
    settings_svc = SettingsService(tmp_path / "s.db")
    settings_svc.set_base_domain("lab.local")
    traefik_svc = MagicMock()
    traefik_svc.rewrite_base_domain.side_effect = OSError("disk full")
    _override(monkeypatch, settings_svc, traefik_svc)
    try:
        resp = _authed_client().post("/settings", data={"base_domain": "other.local"})
        assert resp.status_code == 200
        assert "Não foi possível atualizar as rotas" in resp.text
        assert settings_svc.get_base_domain("home.arpa") == "lab.local"
    finally:
        app.dependency_overrides.clear()


def test_migration_failure_leaves_routes_file_unchanged(monkeypatch, tmp_path):
    settings_svc = SettingsService(tmp_path / "s.db")
    traefik_svc = TraefikService(dynamic_dir=tmp_path / "dyn", base_domain="home.arpa")
    traefik_svc.upsert_route(
        RouteConfig(name="app1", subdomain="app1", target_url="http://app1:80")
    )
    routes_file = tmp_path / "dyn" / "stackpilot-routes.yml"
    before = routes_file.read_text(encoding="utf-8")

    def _boom(data):
        raise OSError("disk full")

    monkeypatch.setattr(traefik_svc, "_save_raw", _boom)
    _override(monkeypatch, settings_svc, traefik_svc)
    try:
        resp = _authed_client().post("/settings", data={"base_domain": "lab.local"})
        assert resp.status_code == 200
        assert "Não foi possível atualizar as rotas" in resp.text
        assert routes_file.read_text(encoding="utf-8") == before
        assert settings_svc.get_base_domain("home.arpa") == "home.arpa"
    finally:
        app.dependency_overrides.clear()
