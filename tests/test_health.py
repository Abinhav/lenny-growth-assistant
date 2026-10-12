from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_endpoint_serves_frontend() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert '<div id="root"></div>' in response.text


def test_health_endpoint_returns_healthy_status() -> None:
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert data["application"] == "The Lenny Growth Assistant"
    assert data["version"] == "0.1.0"
    assert data["environment"] == "development"


def test_api_documentation_is_available() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "paths" in response.json()