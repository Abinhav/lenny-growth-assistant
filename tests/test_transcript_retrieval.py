
import pytest

from app.core.config import get_settings
from app.db.session import get_db_connection
from app.services.transcript_retrieval import (
    MAX_QUERY_LENGTH,
    _build_search_queries,
    _is_promotional_content,
    _prepare_search_query,
    _topic_title_score,
    search_transcript_chunks,
)


def test_prepare_search_query_removes_common_stop_words() -> None:
    query = _prepare_search_query(
        "How should I prioritize the product roadmap?"
    )
    assert query == "prioritize product roadmap"


def test_prepare_search_query_returns_empty_for_blank_input() -> None:
    assert _prepare_search_query("   ") == ""


def test_prepare_search_query_rejects_overlong_input() -> None:
    with pytest.raises(ValueError, match="must not exceed"):
        _prepare_search_query("x" * (MAX_QUERY_LENGTH + 1))


def test_build_search_queries_expands_known_terms() -> None:
    queries = _build_search_queries("prioritize product roadmap")
    assert queries
    assert queries[0] == "prioritize product roadmap"
    assert any("prioritization" in query for query in queries)
    assert any("product strategy" in query for query in queries)


def test_build_search_queries_deduplicates_variants() -> None:
    queries = _build_search_queries("roadmap")
    assert len(queries) == len(set(queries))


def test_promotional_content_is_detected_case_insensitively() -> None:
    assert _is_promotional_content(
        "This episode is brought to you by Example Sponsor."
    )


def test_regular_transcript_content_is_not_promotional() -> None:
    assert not _is_promotional_content(
        "The team interviewed customers before changing onboarding."
    )


@pytest.mark.parametrize("limit", [0, -1, 11])
def test_search_rejects_invalid_limit(limit: int) -> None:
    with pytest.raises(ValueError, match="limit must be between"):
        search_transcript_chunks(None, "product onboarding", limit=limit)


def test_search_returns_empty_for_stop_word_only_query() -> None:
    assert search_transcript_chunks(None, "how should I do it") == []


def test_query_expansions_avoid_generic_unrelated_terms():
    onboarding_queries = _build_search_queries(
        "How can product teams improve user onboarding and activation?"
    )
    roadmap_queries = _build_search_queries(
        "How should a startup prioritize its product roadmap?"
    )
    assert "customer problem" not in onboarding_queries
    assert "user experience" not in onboarding_queries
    assert "what to build" not in roadmap_queries


def test_hiring_query_expands_to_recruiting_terms():
    queries = _build_search_queries("How can a startup improve hiring?")
    assert "improve hiring" in queries
    assert "recruiting" in queries
    assert "recruitment" in queries
    assert "customer problem" not in queries


def test_topic_title_score_rewards_matching_episode_title():
    result = {
        "episode_title": (
            "A framework for finding product-market fit | Todd Jackson"
        )
    }
    score = _topic_title_score(result, {"product", "market", "fit"})
    assert score == 3


def test_topic_title_score_is_zero_without_matching_terms():
    result = {"episode_title": "How to build effective engineering teams"}
    assert _topic_title_score(result, {"product", "market", "fit"}) == 0


def test_database_retrieval_finds_product_market_fit_framework():
    settings = get_settings()
    if not settings.database_url:
        pytest.skip("DATABASE_URL is not configured")

    generator = get_db_connection()
    connection = next(generator)

    try:
        specific_results = search_transcript_chunks(
            connection,
            (
                "product-market fit framework demand satisfaction "
                "efficiency levels customer problem"
            ),
            limit=5,
        )

        broad_results = search_transcript_chunks(
            connection,
            "What are practical ways to improve product-market fit?",
            limit=5,
        )
    finally:
        generator.close()

    assert specific_results, (
        "Expected the specific query to retrieve transcript evidence"
    )

    first_episode = (
        specific_results[0].get("episode_title", "").lower()
    )
    assert "framework for finding product-market fit" in first_episode

    assert broad_results, (
        "Expected the broad query to retrieve transcript evidence"
    )

    relevant_terms = (
        "product-market fit",
        "product market fit",
        "marketplace",
        "superhuman",
    )

    relevant_results = [
        result
        for result in broad_results
        if any(
            term in (
                    (result.get("episode_title") or "").lower()
                    + " "
                    + (result.get("content") or "").lower()
            )
            for term in relevant_terms
        )
    ]

    assert relevant_results, (
        "Expected broad-query results to contain product-market-fit "
        "or closely related marketplace evidence"
    )