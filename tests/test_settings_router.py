from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.dependencies import get_metrics_settings
from app.main import app


def _client():
    c = TestClient(app)
    c.post("/login", data={"username": "admin", "password": "admin"})
    return c


def _store():
    store = MagicMock()
    store.get_refresh_interval.return_value = 10
    return store


def test_settings_requires_auth():
    r = TestClient(app).get("/settings", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_settings_page_shows_interval():
    store = _store()
    store.get_refresh_interval.return_value = 42
    app.dependency_overrides[get_metrics_settings] = lambda: store
    try:
        r = _client().get("/settings")
        assert r.status_code == 200
        assert 'name="interval"' in r.text
        assert 'value="42"' in r.text
    finally:
        app.dependency_overrides.clear()


def test_post_saves_interval():
    store = _store()
    app.dependency_overrides[get_metrics_settings] = lambda: store
    try:
        r = _client().post(
            "/settings/metrics", data={"interval": "30"}, headers={"HX-Request": "true"}
        )
        assert r.status_code == 200
        store.set_refresh_interval.assert_called_once_with(30)
        assert "salvo" in r.text.lower()
    finally:
        app.dependency_overrides.clear()


def test_post_rejects_invalid_interval():
    store = _store()
    store.set_refresh_interval.side_effect = ValueError("faixa")
    app.dependency_overrides[get_metrics_settings] = lambda: store
    try:
        r = _client().post(
            "/settings/metrics", data={"interval": "2"}, headers={"HX-Request": "true"}
        )
        assert r.status_code == 200
        assert "5" in r.text and "900" in r.text
    finally:
        app.dependency_overrides.clear()
