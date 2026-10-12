
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_and_list_session() -> None:
    create_response = client.post(
        "/api/v1/sessions",
        json={
            "title": "Automated test conversation",
            "user_id": "test-user",
        },
    )

    assert create_response.status_code == 201
    created_session = create_response.json()
    session_id = created_session["id"]

    assert created_session["title"] == "Automated test conversation"
    assert created_session["user_id"] == "test-user"

    list_response = client.get("/api/v1/sessions")

    assert list_response.status_code == 200
    assert any(
        session["id"] == session_id
        for session in list_response.json()
    )


def test_create_and_list_messages() -> None:
    session_response = client.post(
        "/api/v1/sessions",
        json={"title": "Message test conversation"},
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    message_response = client.post(
        f"/api/v1/sessions/{session_id}/messages",
        json={
            "role": "user",
            "content": "Test message persistence",
        },
    )

    assert message_response.status_code == 201
    created_message = message_response.json()
    assert created_message["content"] == "Test message persistence"
    assert created_message["session_id"] == session_id

    list_response = client.get(
        f"/api/v1/sessions/{session_id}/messages"
    )

    assert list_response.status_code == 200
    messages = list_response.json()
    assert len(messages) == 1
    assert messages[0]["id"] == created_message["id"]
    assert messages[0]["role"] == "user"


def test_message_for_unknown_session_returns_404() -> None:
    response = client.post(
        "/api/v1/sessions/00000000-0000-0000-0000-000000000000/messages",
        json={
            "role": "user",
            "content": "This should not be saved",
        },
    )

    assert response.status_code == 404


def test_invalid_message_role_is_rejected() -> None:
    session_response = client.post(
        "/api/v1/sessions",
        json={"title": "Validation test"},
    )
    session_id = session_response.json()["id"]

    response = client.post(
        f"/api/v1/sessions/{session_id}/messages",
        json={
            "role": "admin",
            "content": "Invalid role",
        },
    )

    assert response.status_code == 422