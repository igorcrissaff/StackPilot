import re
from pathlib import Path
import yaml
from pydantic import BaseModel, field_validator

DOMAIN_RE = re.compile(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class RouteConfig(BaseModel):
    name: str
    domain: str
    target_url: str
    tls: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_RE.match(v):
            raise ValueError("Route name must be alphanumeric with dashes/underscores")
        return v

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        if not DOMAIN_RE.match(v):
            raise ValueError("Invalid domain name")
        return v

    @field_validator("target_url")
    @classmethod
    def validate_target_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("target_url must start with http:// or https://")
        return v


class TraefikService:
    def __init__(self, dynamic_dir: Path):
        self.dynamic_dir = dynamic_dir
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
        routes = []
        for name, router in routers.items():
            rule = router.get("rule", "")
            domain = rule.removeprefix("Host(`").removesuffix("`)")
            svc_name = router.get("service", name)
            servers = services.get(svc_name, {}).get("loadBalancer", {}).get("servers", [])
            target_url = servers[0]["url"] if servers else ""
            tls = "tls" in router
            routes.append(RouteConfig(name=name, domain=domain, target_url=target_url, tls=tls))
        return routes

    def upsert_route(self, route: RouteConfig) -> None:
        data = self._load_raw()
        router_def: dict = {
            "rule": f"Host(`{route.domain}`)",
            "service": route.name,
            "entryPoints": ["websecure"] if route.tls else ["web"],
        }
        if route.tls:
            router_def["tls"] = {"certResolver": "letsencrypt"}

        data["http"]["routers"][route.name] = router_def
        data["http"]["services"][route.name] = {
            "loadBalancer": {"servers": [{"url": route.target_url}]}
        }
        self._save_raw(data)

    def delete_route(self, name: str) -> bool:
        data = self._load_raw()
        existed = name in data["http"]["routers"]
        data["http"]["routers"].pop(name, None)
        data["http"]["services"].pop(name, None)
        if existed:
            self._save_raw(data)
        return existed
