import pytest
from pydantic import ValidationError

from app.services.traefik_service import RouteConfig, TraefikService


def test_upsert_and_list_routes(tmp_path):
    svc = TraefikService(dynamic_dir=tmp_path)
    route = RouteConfig(name="portainer", domain="portainer.home.arpa", target_url="http://portainer:9000", tls=True)
    svc.upsert_route(route)

    routes = svc.list_routes()
    assert len(routes) == 1
    assert routes[0].name == "portainer"
    assert routes[0].domain == "portainer.home.arpa"
    assert routes[0].target_url == "http://portainer:9000"
    assert routes[0].tls is True


def test_delete_route(tmp_path):
    svc = TraefikService(dynamic_dir=tmp_path)
    svc.upsert_route(RouteConfig(name="app1", domain="app1.local", target_url="http://app1:8080", tls=False))

    assert svc.delete_route("app1") is True
    assert svc.list_routes() == []
    assert svc.delete_route("nonexistent") is False


def test_invalid_domain_or_url_rejected(tmp_path):
    with pytest.raises(ValidationError):
        RouteConfig(name="bad", domain="invalid domain!", target_url="http://app:80")

    with pytest.raises(ValidationError):
        RouteConfig(name="bad", domain="app.local", target_url="not-a-url")
