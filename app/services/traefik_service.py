import re
from pathlib import Path
import yaml
from pydantic import BaseModel, field_validator

SUBDOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class RouteConfig(BaseModel):
    name: str
    subdomain: str
    target_url: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_RE.match(v):
            raise ValueError("Route name must be alphanumeric with dashes/underscores")
        return v

    @field_validator("subdomain")
    @classmethod
    def validate_subdomain(cls, v: str) -> str:
        v = v.strip().lower()
        if not SUBDOMAIN_RE.match(v):
            raise ValueError("Invalid subdomain")
        return v

    @field_validator("target_url")
    @classmethod
    def validate_target_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("target_url must start with http:// or https://")
        return v


class TraefikService:
    def __init__(self, dynamic_dir: Path, base_domain: str):
        self.dynamic_dir = dynamic_dir
        self.base_domain = base_domain.strip().lower().rstrip(".")
        self.config_file = self.dynamic_dir / "stackpilot-routes.yml"

    def _load_raw(self) -> dict:
        if not self.config_file.exists():
            return {"http": {"routers": {}, "services": {}}}
        data = yaml.safe_load(self.config_file.read_text(encoding="utf-8")) or {}
        http = data.setdefault("http", {})
        http.setdefault("routers", {})
        http.setdefault("services", {})
        return data

    def _save_raw(self, data: dict) -> None:
        self.dynamic_dir.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    def list_routes(self) -> list[RouteConfig]:
        data = self._load_raw()
        routers = data["http"]["routers"]
        services = data["http"]["services"]
        suffix = f".{self.base_domain}"
        routes = []
        for name, router in routers.items():
            rule = router.get("rule", "")
            domain = rule.removeprefix("Host(`").removesuffix("`)")
            if not domain.endswith(suffix):
                continue
            subdomain = domain[: -len(suffix)]
            if not SUBDOMAIN_RE.match(subdomain):
                continue
            svc_name = router.get("service", name)
            servers = services.get(svc_name, {}).get("loadBalancer", {}).get("servers", [])
            target_url = servers[0]["url"] if servers else ""
            routes.append(RouteConfig(name=name, subdomain=subdomain, target_url=target_url))
        return routes

    def get_route(self, name: str) -> RouteConfig | None:
        for route in self.list_routes():
            if route.name == name:
                return route
        return None

    def upsert_route(self, route: RouteConfig) -> None:
        data = self._load_raw()
        router_def: dict = {
            "rule": f"Host(`{route.subdomain}.{self.base_domain}`)",
            "service": route.name,
            "entryPoints": ["web"],
        }

        data["http"]["routers"][route.name] = router_def
        data["http"]["services"][route.name] = {
            "loadBalancer": {"servers": [{"url": route.target_url}]}
        }
        self._save_raw(data)

    def rewrite_base_domain(self, old: str, new: str) -> int:
        old = old.strip().lower().rstrip(".")
        new = new.strip().lower().rstrip(".")
        if old == new:
            return 0

        data = self._load_raw()
        routers = data["http"]["routers"]
        old_suffix = f".{old}"
        count = 0
        for router in routers.values():
            rule = router.get("rule", "")
            domain = rule.removeprefix("Host(`").removesuffix("`)")
            if not domain.endswith(old_suffix):
                continue
            subdomain = domain[: -len(old_suffix)]
            if not SUBDOMAIN_RE.match(subdomain):
                continue
            router["rule"] = f"Host(`{subdomain}.{new}`)"
            count += 1

        if count > 0:
            self._save_raw(data)
        return count

    def delete_route(self, name: str) -> bool:
        data = self._load_raw()
        existed = name in data["http"]["routers"]
        data["http"]["routers"].pop(name, None)
        data["http"]["services"].pop(name, None)
        if existed:
            self._save_raw(data)
        return existed
