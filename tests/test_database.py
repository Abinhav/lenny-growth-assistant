
import psycopg
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_database_connection_from_settings() -> None:
    settings = get_settings()

    assert settings.database_url, "DATABASE_URL is not configured"

    with psycopg.connect(
            settings.database_url,
            connect_timeout=5,
    ) as connection:
        row = connection.execute(
            "SELECT current_database()"
        ).fetchone()

    assert row is not None
    assert row[0] == "lenny_growth_assistant"


def test_health_endpoint_still_works() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"

