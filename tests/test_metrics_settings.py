import pytest

from app.services.metrics_settings import (
    DEFAULT_REFRESH_SECONDS,
    MetricsSettingsStore,
)


def test_default_interval(tmp_path):
    store = MetricsSettingsStore(tmp_path / "m.db")
    assert store.get_refresh_interval() == DEFAULT_REFRESH_SECONDS


def test_persists_interval(tmp_path):
    path = tmp_path / "m.db"
    MetricsSettingsStore(path).set_refresh_interval(5)
    assert MetricsSettingsStore(path).get_refresh_interval() == 5
    MetricsSettingsStore(path).set_refresh_interval(900)
    assert MetricsSettingsStore(path).get_refresh_interval() == 900


@pytest.mark.parametrize("value", [4, 901, 0, -1])
def test_rejects_out_of_range(tmp_path, value):
    store = MetricsSettingsStore(tmp_path / "m.db")
    with pytest.raises(ValueError):
        store.set_refresh_interval(value)


@pytest.mark.parametrize("value", ["abc", 10.5, None])
def test_rejects_non_integer(tmp_path, value):
    store = MetricsSettingsStore(tmp_path / "m.db")
    with pytest.raises(ValueError):
        store.set_refresh_interval(value)
