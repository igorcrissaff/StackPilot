from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any
import yaml
from pydantic import BaseModel

from app.services.docker_service import DockerService


STACK_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class ComposeInfo(BaseModel):
    container_id: str
    container_name: str
    stack_name: str
    service_name: str
    file_path: Path
    compose_content: str
    env_path: Path | None = None
    env_content: str | None = None
    is_generated: bool = False
    exists_on_disk: bool = False


class ComposeService:
    def __init__(
        self,
        docker_service: DockerService,
        stacks_dir: Path | str | None = None,
        compose_up_timeout: int = 120,
        default_network: str = "stackpilot_net",
    ):
        self.docker_service = docker_service
        self.stacks_dir = Path(stacks_dir) if stacks_dir else Path("/opt/stacks")
        self.compose_up_timeout = compose_up_timeout
        self.default_network = default_network

    def _resolve_stacks_dir(self) -> Path:
        if self.stacks_dir.exists():
            return self.stacks_dir
        # Fallback to local ./stacks directory
        local_stacks = Path.cwd() / "stacks"
        if local_stacks.exists():
            return local_stacks
        return self.stacks_dir

    def validate_compose_yaml(self, content: str) -> tuple[bool, str | None, dict[str, Any] | None]:
        if not content or not content.strip():
            return False, "O conteúdo do arquivo compose não pode estar vazio.", None
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            if mark:
                msg = f"Erro de sintaxe no YAML (linha {mark.line + 1}, coluna {mark.column + 1}): {getattr(exc, 'problem', str(exc))}"
            else:
                msg = f"Erro de sintaxe no YAML: {exc}"
            return False, msg, None

        if not isinstance(data, dict):
            return False, "O arquivo Compose deve ser um mapeamento YAML (objeto).", None

        if "services" not in data or not isinstance(data["services"], dict):
            return False, "O arquivo Compose deve conter uma seção 'services' com mapeamento de serviços.", None

        if len(data["services"]) == 0:
            return False, "A seção 'services' deve conter ao menos um serviço definido.", None

        return True, None, data

    def derive_service_name(self, image_ref: str) -> str:
        ref = image_ref.strip()
        if ref.startswith("sha256:"):
            return "image-" + ref.removeprefix("sha256:")[:12]

        if "@" in ref:
            ref = ref.split("@", 1)[0]

        colon = ref.rfind(":")
        if colon != -1 and "/" not in ref[colon:]:
            ref = ref[:colon]

        name = ref.rsplit("/", 1)[-1].lower()
        name = re.sub(r"[^a-z0-9._-]", "-", name)
        if not name:
            return "app"
        if name[0].isdigit():
            return f"app-{name}"
        return name

    def generate_starter_compose(self, image_ref: str) -> str:
        service = self.derive_service_name(image_ref)
        data = {
            "services": {
                service: {
                    "image": image_ref,
                    "restart": "unless-stopped",
                    "networks": [self.default_network],
                }
            },
            "networks": {self.default_network: {"external": True}},
        }
        return yaml.safe_dump(data, sort_keys=False, default_flow_style=False)

    def extract_images(self, compose_content: str) -> list[str]:
        data = yaml.safe_load(compose_content) or {}
        services = data.get("services") or {}
        images: list[str] = []
        for service in services.values():
            if isinstance(service, dict) and "image" in service:
                images.append(str(service["image"]))
        return images

    def _run_compose_up(self, file_path: Path) -> tuple[bool, str, bool]:
        cwd = str(file_path.parent)
        cmd = ["docker", "compose", "-f", str(file_path), "up", "-d", "--remove-orphans"]
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.compose_up_timeout,
            )
            output = (proc.stdout + "\n" + proc.stderr).strip()
            return proc.returncode == 0, output, False
        except (FileNotFoundError, OSError):
            pass

        cmd_v1 = ["docker-compose", "-f", str(file_path), "up", "-d"]
        try:
            proc = subprocess.run(
                cmd_v1,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.compose_up_timeout,
            )
            output = (proc.stdout + "\n" + proc.stderr).strip()
            return proc.returncode == 0, output, False
        except (FileNotFoundError, OSError):
            return False, "", True

    def create_stack(
        self,
        stack_name: str,
        compose_content: str,
        env_content: str | None = None,
    ) -> tuple[bool, str]:
        name = stack_name.strip().lower()
        if not STACK_NAME_RE.match(name):
            return (
                False,
                f"Nome de stack inválido: {stack_name!r}. Use letras minúsculas, números, '-' e '_'.",
            )

        is_valid, error_msg, _ = self.validate_compose_yaml(compose_content)
        if not is_valid:
            return False, error_msg or "Arquivo Compose inválido."

        base = self._resolve_stacks_dir().resolve()
        target = (base / name).resolve()
        if base != target and base not in target.parents:
            return False, "Caminho de stack inválido."

        if target.exists():
            return False, f"A stack '{name}' já existe em {target}."

        target.mkdir(parents=True, exist_ok=True)
        file_path = target / "compose.yaml"
        file_path.write_text(compose_content, encoding="utf-8")
        if env_content and env_content.strip():
            (target / ".env").write_text(env_content, encoding="utf-8")

        ok, output, cli_missing = self._run_compose_up(file_path)
        if not ok:
            shutil.rmtree(target, ignore_errors=True)
            if cli_missing:
                return False, "O comando 'docker compose' não foi encontrado no PATH."
            return False, f"Falha ao implantar a stack '{name}':\n{output}"

        message = f"Stack '{name}' criada e implantada com sucesso!"
        if output:
            message = f"{message}\n{output}"
        return True, message

    def get_compose_info(self, container_id: str) -> ComposeInfo:
        container = self.docker_service.get_container(container_id)
        raw_labels = getattr(container, "labels", None)
        labels = raw_labels if isinstance(raw_labels, dict) else {}

        container_name = container.name.lstrip("/")
        stack_name = labels.get("com.docker.compose.project") or container_name
        service_name = labels.get("com.docker.compose.service") or container_name

        existing_file = self._find_existing_compose_file(container, labels, stack_name)

        if existing_file and existing_file.is_file():
            resolved_file = existing_file.resolve()
            compose_content = resolved_file.read_text(encoding="utf-8")

            # Look for companion .env
            env_file = resolved_file.parent / ".env"
            env_content = None
            env_path = None
            if env_file.is_file():
                env_path = env_file.resolve()
                env_content = env_path.read_text(encoding="utf-8")

            return ComposeInfo(
                container_id=container_id,
                container_name=container_name,
                stack_name=stack_name,
                service_name=service_name,
                file_path=resolved_file,
                compose_content=compose_content,
                env_path=env_path,
                env_content=env_content,
                is_generated=False,
                exists_on_disk=True,
            )

        # File does not exist on disk: generate compose specification
        target_dir = self._resolve_stacks_dir() / stack_name
        target_file = target_dir / "compose.yaml"
        generated_content = self._generate_compose_yaml(container, service_name, container_name)

        return ComposeInfo(
            container_id=container_id,
            container_name=container_name,
            stack_name=stack_name,
            service_name=service_name,
            file_path=target_file,
            compose_content=generated_content,
            env_path=None,
            env_content=None,
            is_generated=True,
            exists_on_disk=False,
        )

    def _find_existing_compose_file(
        self,
        container: Any,
        labels: dict[str, str],
        stack_name: str,
    ) -> Path | None:
        candidates: list[Path] = []

        # 1. Label com.docker.compose.project.config_files
        config_files_label = labels.get("com.docker.compose.project.config_files")
        if config_files_label:
            for p_str in config_files_label.split(","):
                p_clean = p_str.strip()
                if p_clean:
                    candidates.append(Path(p_clean))
                    candidates.append(Path.cwd() / p_clean)
                    candidates.append(Path.cwd() / Path(p_clean).name)

        # 2. Label com.docker.compose.project.working_dir
        working_dir_label = labels.get("com.docker.compose.project.working_dir")
        if working_dir_label:
            wdir = Path(working_dir_label)
            for fname in ("compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml"):
                candidates.append(wdir / fname)
                candidates.append(self._resolve_stacks_dir() / wdir.name / fname)

        # 3. Standard Dockge / stackpilot stacks dir structure
        stacks_base = self._resolve_stacks_dir()
        for fname in ("compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml"):
            candidates.append(stacks_base / stack_name / fname)
            candidates.append(Path.cwd() / "stacks" / stack_name / fname)

        # 4. Check current working directory only if stack matches current directory
        if stack_name.lower() in (Path.cwd().name.lower(), "stackpilot"):
            for fname in ("compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml"):
                candidates.append(Path.cwd() / fname)

        for candidate in candidates:
            try:
                if candidate.is_file():
                    return candidate
            except (OSError, ValueError):
                continue

        return None

    def _generate_compose_yaml(self, container: Any, service_name: str, container_name: str) -> str:
        attrs = getattr(container, "attrs", {}) or {}
        config = attrs.get("Config", {}) or {}
        host_config = attrs.get("HostConfig", {}) or {}
        network_settings = attrs.get("NetworkSettings", {}) or {}

        # Image
        image_tag = ""
        if getattr(container, "image", None) and getattr(container.image, "tags", None):
            image_tag = container.image.tags[0]
        if not image_tag:
            image_tag = config.get("Image", "latest")

        service_dict: dict[str, Any] = {
            "image": image_tag,
            "container_name": container_name,
        }

        # Restart policy
        restart_policy = host_config.get("RestartPolicy", {}).get("Name", "")
        if restart_policy:
            service_dict["restart"] = restart_policy
        else:
            service_dict["restart"] = "unless-stopped"

        # Ports
        port_bindings = host_config.get("PortBindings") or {}
        ports_list = []
        for container_port, host_list in port_bindings.items():
            c_port = container_port.split("/")[0]
            if host_list:
                for binding in host_list:
                    h_port = binding.get("HostPort")
                    h_ip = binding.get("HostIp", "")
                    if h_port:
                        if h_ip:
                            ports_list.append(f"{h_ip}:{h_port}:{c_port}")
                        else:
                            ports_list.append(f"{h_port}:{c_port}")
            else:
                ports_list.append(c_port)
        if ports_list:
            service_dict["ports"] = sorted(list(set(ports_list)))

        # Environment
        env_list = config.get("Env") or []
        filtered_env = []
        # Filter out common OS-level variables if desired, or keep user vars
        system_vars = {"PATH", "HOSTNAME", "HOME"}
        for item in env_list:
            if isinstance(item, str) and "=" in item:
                k, _ = item.split("=", 1)
                if k not in system_vars:
                    filtered_env.append(item)
        if filtered_env:
            service_dict["environment"] = filtered_env

        # Volumes / Binds
        binds = host_config.get("Binds") or []
        if binds:
            service_dict["volumes"] = binds

        # Networks
        networks = network_settings.get("Networks") or {}
        net_names = [n for n in networks.keys() if n not in ("bridge", "host", "none", "default")]
        if net_names:
            service_dict["networks"] = net_names

        compose_dict: dict[str, Any] = {
            "services": {
                service_name: service_dict
            }
        }

        if net_names:
            compose_dict["networks"] = {net: {"external": True} for net in net_names}

        return yaml.dump(compose_dict, sort_keys=False, default_flow_style=False)

    def save_compose_file(
        self,
        container_id: str,
        compose_content: str,
        env_content: str | None = None,
        custom_path: Path | None = None,
    ) -> Path:
        is_valid, error_msg, _ = self.validate_compose_yaml(compose_content)
        if not is_valid:
            raise ValueError(error_msg)

        if custom_path is not None:
            target_path = Path(custom_path)
        else:
            info = self.get_compose_info(container_id)
            target_path = info.file_path

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(compose_content, encoding="utf-8")

        if env_content is not None and env_content.strip():
            env_path = target_path.parent / ".env"
            env_path.write_text(env_content, encoding="utf-8")

        return target_path

    def deploy_compose(
        self,
        container_id: str,
        compose_content: str,
        env_content: str | None = None,
    ) -> tuple[bool, str]:
        # 1. Validate & Save
        try:
            file_path = self.save_compose_file(container_id, compose_content, env_content)
        except ValueError as exc:
            return False, str(exc)

        # 2. Execute docker compose up
        ok, output, cli_missing = self._run_compose_up(file_path)
        if ok:
            msg = (
                f"Stack implantada com sucesso!\n{output}"
                if output
                else "Stack implantada com sucesso!"
            )
            return True, msg
        if not cli_missing:
            return False, f"Falha ao executar 'docker compose up':\n{output}"

        # Fallback to restarting the container directly via DockerService
        try:
            self.docker_service.container_action(container_id, "restart")
            return True, (
                f"Arquivo salvo com sucesso em {file_path}!\n"
                "Aviso: O comando 'docker compose' não foi encontrado no PATH do sistema. "
                "O container foi reiniciado diretamente através do Docker socket."
            )
        except Exception as exc:
            return True, (
                f"Arquivo salvo com sucesso em {file_path}!\n"
                f"Aviso: O comando 'docker compose' não está disponível e o reinício falhou: {exc}."
            )
