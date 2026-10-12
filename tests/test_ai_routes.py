from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def sample_transcript_chunks() -> list[dict]:
    return [
        {
            "guest": "Example Guest",
            "episode_title": "Understanding Product-Market Fit",
            "source_path": "episodes/product-market-fit.md",
            "source_url": "https://example.com/transcript",
            "start_timestamp": "00:10:00",
            "end_timestamp": "00:12:00",
            "content": (
                "Teams can learn about product-market fit by talking "
                "to customers and examining whether the product solves "
                "a meaningful problem for them."
            ),
        }
    ]


def test_essay_mode_includes_writing_skill() -> None:
    with (
        patch(
            "app.api.routes.ai.get_db_connection",
        ) as mock_db,
        patch(
            "app.api.routes.ai.search_transcript_chunks",
            return_value=sample_transcript_chunks(),
        ),
        patch(
            "app.api.routes.ai.generate_response",
            return_value=("Test essay response [Guest: Example Guest, Episode: Understanding Product-Market Fit, Timestamp: 00:10:00, URL: https://example.com/transcript]"),
        ) as mock_generate,
    ):
        mock_connection = mock_db.return_value.__next__.return_value

        response = client.post(
            "/api/v1/ai/generate",
            json={
                "prompt": "Write an essay about product-market fit.",
                "writing_mode": "essay",
            },
        )

    assert response.status_code == 200
    assert response.json()["response"].startswith("Test essay response")

    sent_prompt = mock_generate.call_args.args[0]
    assert "Ship 30 for 30" in sent_prompt
    assert "product-market fit" in sent_prompt
    assert "Never invent citations, URLs, timestamps, quotes, or facts." in sent_prompt
    assert "Understanding Product-Market Fit" in sent_prompt



def test_general_mode_does_not_add_writing_skill() -> None:
    with (
        patch(
            "app.api.routes.ai.get_db_connection",
        ) as mock_db,
        patch(
            "app.api.routes.ai.search_transcript_chunks",
            return_value=sample_transcript_chunks(),
        ),
        patch(
            "app.api.routes.ai.generate_response",
            return_value=("General response [Guest: Example Guest, Episode: Understanding Product-Market Fit, Timestamp: 00:10:00, URL: https://example.com/transcript]"),
        ) as mock_generate,
    ):
        mock_db.return_value.__next__.return_value = object()

        response = client.post(
            "/api/v1/ai/generate",
            json={"prompt": "How can a team understand product-market fit?"},
        )

    assert response.status_code == 200
    assert response.json()["response"].startswith("General response")

    sent_prompt = mock_generate.call_args.args[0]
    assert "Ship 30 for 30" not in sent_prompt
    assert "only the supplied" in sent_prompt
    assert "Understanding Product-Market Fit" in sent_prompt
    assert "How can a team understand product-market fit?" in sent_prompt



def test_invalid_writing_mode_is_rejected() -> None:
    response = client.post(
        "/api/v1/ai/generate",
        json={
            "prompt": "Write an essay.",
            "writing_mode": "unknown",
        },
    )

    assert response.status_code == 422


def test_essay_mode_returns_safe_response_without_evidence() -> None:
    with (
        patch("app.api.routes.ai.get_db_connection") as mock_db,
        patch(
            "app.api.routes.ai.search_transcript_chunks",
            return_value=[],
        ),
        patch(
            "app.api.routes.ai.generate_response",
        ) as mock_generate,
    ):
        mock_db.return_value.__next__.return_value = object()

        response = client.post(
            "/api/v1/ai/generate",
            json={
                "prompt": "Write an essay about an unsupported topic.",
                "writing_mode": "essay",
            },
        )

    assert response.status_code == 200
    assert "couldn't find sufficiently relevant evidence" in (
        response.json()["response"]
    ).lower()
    mock_generate.assert_not_called()
