import pytest

from app.services.settings_service import (
    BASE_DOMAIN_KEY,
    GLOBAL_SCOPE,
    SettingsService,
)


def _svc(tmp_path):
    return SettingsService(tmp_path / "settings.db")


def test_set_get_roundtrip(tmp_path):
    svc = _svc(tmp_path)
    svc.set(GLOBAL_SCOPE, "x", "1")
    assert svc.get(GLOBAL_SCOPE, "x") == "1"
    assert svc.get(GLOBAL_SCOPE, "missing") is None


def test_all_and_delete(tmp_path):
    svc = _svc(tmp_path)
    svc.set(GLOBAL_SCOPE, "a", "1")
    svc.set(GLOBAL_SCOPE, "b", "2")
    assert svc.all(GLOBAL_SCOPE) == {"a": "1", "b": "2"}
    svc.delete(GLOBAL_SCOPE, "a")
    assert svc.all(GLOBAL_SCOPE) == {"b": "2"}


def test_get_base_domain_falls_back_to_default(tmp_path):
    svc = _svc(tmp_path)
    assert svc.get_base_domain("home.arpa") == "home.arpa"


def test_set_base_domain_normalizes_and_overrides(tmp_path):
    svc = _svc(tmp_path)
    assert svc.set_base_domain(" Lab.Local. ") == "lab.local"
    assert svc.get_base_domain("home.arpa") == "lab.local"
    assert svc.get(GLOBAL_SCOPE, BASE_DOMAIN_KEY) == "lab.local"


def test_set_base_domain_rejects_invalid(tmp_path):
    svc = _svc(tmp_path)
    with pytest.raises(ValueError):
        svc.set_base_domain("http://lab.local")
    assert svc.get(GLOBAL_SCOPE, BASE_DOMAIN_KEY) is None


def test_reset_base_domain_reverts_to_default(tmp_path):
    svc = _svc(tmp_path)
    svc.set_base_domain("lab.local")
    svc.reset_base_domain()
    assert svc.get_base_domain("home.arpa") == "home.arpa"
