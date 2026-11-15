import pytest
import yaml
from pydantic import ValidationError

from app.services.traefik_service import RouteConfig, TraefikService


def test_upsert_writes_http_router_under_base_domain(tmp_path):
    svc = TraefikService(dynamic_dir=tmp_path, base_domain="home.arpa")
    svc.upsert_route(
        RouteConfig(name="portainer-ui", subdomain="portainer", target_url="http://portainer:9000")
    )

    data = yaml.safe_load((tmp_path / "stackpilot-routes.yml").read_text(encoding="utf-8"))
    router = data["http"]["routers"]["portainer-ui"]
    assert router["rule"] == "Host(`portainer.home.arpa`)"
    assert router["entryPoints"] == ["web"]
    assert router["service"] == "portainer-ui"
    assert "tls" not in router
    assert data["http"]["services"]["portainer-ui"]["loadBalancer"]["servers"][0]["url"] == "http://portainer:9000"


def test_list_routes_returns_subdomain(tmp_path):
    svc = TraefikService(dynamic_dir=tmp_path, base_domain="home.arpa")
    svc.upsert_route(RouteConfig(name="grafana", subdomain="grafana", target_url="http://grafana:3000"))

    routes = svc.list_routes()
    assert len(routes) == 1
    assert routes[0].name == "grafana"
    assert routes[0].subdomain == "grafana"
    assert routes[0].target_url == "http://grafana:3000"


def test_subdomain_is_normalized_and_dots_rejected():
    assert RouteConfig(name="x", subdomain=" Grafana ", target_url="http://g:3000").subdomain == "grafana"
    with pytest.raises(ValidationError):
        RouteConfig(name="x", subdomain="grafana.home.arpa", target_url="http://g:3000")


def test_list_routes_ignores_routers_outside_base_domain(tmp_path):
    (tmp_path / "stackpilot-routes.yml").write_text(
        yaml.safe_dump(
            {
                "http": {
                    "routers": {
                        "keep": {"rule": "Host(`keep.home.arpa`)", "service": "keep"},
                        "other": {"rule": "Host(`other.example`)", "service": "other"},
                    },
                    "services": {
                        "keep": {"loadBalancer": {"servers": [{"url": "http://keep:80"}]}},
                        "other": {"loadBalancer": {"servers": [{"url": "http://other:80"}]}},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    svc = TraefikService(dynamic_dir=tmp_path, base_domain="home.arpa")
    assert [r.name for r in svc.list_routes()] == ["keep"]

    svc.upsert_route(RouteConfig(name="new", subdomain="new", target_url="http://new:80"))
    data = yaml.safe_load((tmp_path / "stackpilot-routes.yml").read_text(encoding="utf-8"))
    assert data["http"]["routers"]["other"]["rule"] == "Host(`other.example`)"


def test_get_and_delete_route(tmp_path):
    svc = TraefikService(dynamic_dir=tmp_path, base_domain="home.arpa")
    svc.upsert_route(RouteConfig(name="app1", subdomain="app1", target_url="http://app1:8080"))

    found = svc.get_route("app1")
    assert found is not None and found.subdomain == "app1"
    assert svc.delete_route("app1") is True
    assert svc.list_routes() == []
    assert svc.delete_route("missing") is False


def test_invalid_target_url_rejected():
    with pytest.raises(ValidationError):
        RouteConfig(name="bad", subdomain="bad", target_url="not-a-url")


def test_rewrite_base_domain_moves_managed_routers(tmp_path):
    svc = TraefikService(dynamic_dir=tmp_path, base_domain="home.arpa")
    svc.upsert_route(RouteConfig(name="app1", subdomain="app1", target_url="http://app1:80"))

    assert svc.rewrite_base_domain("home.arpa", "lab.local") == 1

    data = yaml.safe_load((tmp_path / "stackpilot-routes.yml").read_text(encoding="utf-8"))
    assert data["http"]["routers"]["app1"]["rule"] == "Host(`app1.lab.local`)"
    assert data["http"]["services"]["app1"]["loadBalancer"]["servers"][0]["url"] == "http://app1:80"


def test_rewrite_base_domain_preserves_other_domains(tmp_path):
    (tmp_path / "stackpilot-routes.yml").write_text(
        yaml.safe_dump(
            {
                "http": {
                    "routers": {
                        "keep": {"rule": "Host(`keep.home.arpa`)", "service": "keep"},
                        "other": {"rule": "Host(`other.example`)", "service": "other"},
                    },
                    "services": {
                        "keep": {"loadBalancer": {"servers": [{"url": "http://keep:80"}]}},
                        "other": {"loadBalancer": {"servers": [{"url": "http://other:80"}]}},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    svc = TraefikService(dynamic_dir=tmp_path, base_domain="home.arpa")

    assert svc.rewrite_base_domain("home.arpa", "lab.local") == 1

    data = yaml.safe_load((tmp_path / "stackpilot-routes.yml").read_text(encoding="utf-8"))
    assert data["http"]["routers"]["keep"]["rule"] == "Host(`keep.lab.local`)"
    assert data["http"]["routers"]["other"]["rule"] == "Host(`other.example`)"


def test_rewrite_base_domain_same_domain_is_noop(tmp_path):
    svc = TraefikService(dynamic_dir=tmp_path, base_domain="home.arpa")
    svc.upsert_route(RouteConfig(name="app1", subdomain="app1", target_url="http://app1:80"))
    assert svc.rewrite_base_domain("home.arpa", "home.arpa") == 0
