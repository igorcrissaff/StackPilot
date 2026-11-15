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
    stack: str | None = None
    service: str | None = None
    compose_file: str | None = None


class ImageInfo(BaseModel):
    id: str
    short_id: str
    tags: list[str]
    size: int
    created: str


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
            raw_labels = getattr(c, "labels", None)
            labels = raw_labels if isinstance(raw_labels, dict) else {}
            result.append(
                ContainerInfo(
                    id=c.id,
                    short_id=c.short_id,
                    name=c.name,
                    image=image_tag,
                    status=c.status,
                    stack=labels.get("com.docker.compose.project"),
                    service=labels.get("com.docker.compose.service"),
                    compose_file=labels.get("com.docker.compose.project.config_files"),
                )
            )
        return result

    def list_images(self) -> list[ImageInfo]:
        try:
            images = self._get_client().images.list()
        except DockerException as exc:
            raise DockerUnavailableError(f"Docker daemon unavailable: {exc}") from exc

        return [
            ImageInfo(
                id=img.id,
                short_id=img.short_id,
                tags=list(img.tags or []),
                size=int(img.attrs.get("Size", 0)),
                created=img.attrs.get("Created", ""),
            )
            for img in images
        ]

    def get_container(self, container_id: str):
        try:
            return self._get_client().containers.get(container_id)
        except NotFound as exc:
            raise ContainerNotFoundError(f"Container {container_id} not found") from exc
        except DockerException as exc:
            raise DockerUnavailableError(f"Docker daemon unavailable: {exc}") from exc

    def container_action(self, container_id: str, action: str) -> None:
        container = self.get_container(container_id)

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
        container = self.get_container(container_id)
        try:
            raw = container.logs(tail=tail)
            return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        except DockerException as exc:
            raise DockerUnavailableError(f"Docker daemon unavailable: {exc}") from exc
