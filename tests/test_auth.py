from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.dependencies import get_docker_service


def test_unauthenticated_redirects_to_login():
    client = TestClient(app)
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_login_invalid_credentials():
    client = TestClient(app)
    resp = client.post("/login", data={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_login_valid_credentials_and_logout():
    mock_docker = MagicMock()
    mock_docker.list_containers.return_value = []
    mock_docker.list_images.return_value = []

    app.dependency_overrides[get_docker_service] = lambda: mock_docker
    try:
        client = TestClient(app)
        resp = client.post(
            "/login",
            data={"username": "admin", "password": "admin"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

        resp_dash = client.get("/")
        assert resp_dash.status_code == 200
        assert "StackPilot" in resp_dash.text

        resp_logout = client.post("/logout", follow_redirects=False)
        assert resp_logout.status_code == 303
        assert resp_logout.headers["location"] == "/login"
    finally:
        app.dependency_overrides.clear()
