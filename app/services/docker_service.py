import docker
from docker.errors import DockerException, NotFound
from pydantic import BaseModel


class DockerUnavailableError(Exception):
    pass


class ContainerNotFoundError(Exception):
    pass


class ContainerInfo(BaseModel):
    id: str
    short_id: str
    name: str
    image: str
    status: str


class DockerService:
    def __init__(self, client: docker.DockerClient | None = None):
        self._client = client

    def _get_client(self) -> docker.DockerClient:
        if self._client is not None:
            return self._client
        try:
            self._client = docker.from_env()
            return self._client
        except DockerException as exc:
            raise DockerUnavailableError(f"Docker daemon unavailable: {exc}") from exc

    def list_containers(self) -> list[ContainerInfo]:
        try:
            containers = self._get_client().containers.list(all=True)
        except DockerException as exc:
            raise DockerUnavailableError(f"Docker daemon unavailable: {exc}") from exc

        result = []
        for c in containers:
            image_tag = c.image.tags[0] if c.image.tags else str(c.image.short_id)
            result.append(
                ContainerInfo(
                    id=c.id,
                    short_id=c.short_id,
                    name=c.name,
                    image=image_tag,
                    status=c.status,
                )
            )
        return result

    def container_action(self, container_id: str, action: str) -> None:
        try:
            container = self._get_client().containers.get(container_id)
        except NotFound as exc:
            raise ContainerNotFoundError(f"Container {container_id} not found") from exc
        except DockerException as exc:
            raise DockerUnavailableError(f"Docker daemon unavailable: {exc}") from exc

        if action == "start":
            container.start()
        elif action == "stop":
            container.stop()
        elif action == "restart":
            container.restart()
        elif action == "remove":
            container.remove(force=True)
        else:
            raise ValueError(f"Unsupported action: {action}")

    def get_logs(self, container_id: str, tail: int = 100) -> str:
        try:
            container = self._get_client().containers.get(container_id)
            raw = container.logs(tail=tail)
            return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        except NotFound as exc:
            raise ContainerNotFoundError(f"Container {container_id} not found") from exc
        except DockerException as exc:
            raise DockerUnavailableError(f"Docker daemon unavailable: {exc}") from exc
