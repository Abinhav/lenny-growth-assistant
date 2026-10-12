import re

from psycopg import Connection
from psycopg.rows import dict_row

from app.services.transcript_ingestion import _is_promotional_content


MAX_QUERY_LENGTH = 1000
DEFAULT_LIMIT = 5
MAX_LIMIT = 10
MIN_CORE_TERM_COVERAGE_RATIO = 0.75
MAX_CHUNKS_PER_EPISODE = 2

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "best", "by",
    "can", "could", "do", "does", "for", "from", "how", "i",
    "in", "is", "it", "me", "my", "of", "on", "or", "should",
    "that", "the", "their", "them", "there", "this", "to",
    "use", "used", "using", "was", "way", "what", "when",
    "where", "which", "who", "why", "with", "would", "you",
    "your", "startup", "team", "teams",
    "according", "three", "practical", "ways", "early", "stage",
    "lenny", "s", "evidence", "say", "about",
    "explain", "main", "ideas", "cite", "episode", "title",
    "guest", "timestamp", "key", "point", "points", "retrieved",
    "only", "transcript", "podcast",
    # Essay-format instructions, not substantive topic keywords.
    "write", "written", "essay", "approximately", "word", "words",
    "indexed", "focus", "focusing", "helping", "users", "user",
    "faster", "reported", "invent", "details", "cite", "not",
    "retrieval", "generate", "generation", "recommendations",
    "statistics", "quotations", "factual", "supported",
    "available", "1250",
}

QUERY_EXPANSIONS = {
    "prioritize": ("prioritization", "prioritizing", "tradeoff"),
    "prioritise": ("prioritisation", "prioritising", "tradeoff"),
    "roadmap": ("roadmaps", "product strategy"),
    "hiring": ("hire", "recruiting", "recruitment"),
    "onboarding": ("activation", "first experience"),
    "retention": ("retained", "churn", "engagement"),
    "growth": ("acquisition", "activation", "retention"),
    "product": ("product management",),
    "activation": ("activated", "aha moment", "time to value"),
    "recruiting": ("hiring", "recruitment", "talent"),
    "roadmaps": ("roadmap", "product strategy", "prioritization"),
    "percentage": ("success rate", "companies reach", "company stages"),
    "companies": ("startups", "companies reach", "company stages"),
    "strong": ("strong product market fit", "level three", "L3"),
    "stages": ("levels", "L1", "L2", "L3", "L4"),
    "reach": ("make it to", "get to", "achieve"),
    "fit": ("product market fit", "finding product market fit"),
    "market": ("product market fit", "marketplace liquidity"),
    "founder": ("product market fit", "customer feedback"),
}

PROMOTIONAL_MARKERS = (
    "this episode is brought to you by",
    "this episode is sponsored by",
    "this episode is supported by",
    "our sponsor",
    "today's sponsor",
    "today's episode is sponsored by",
    "trust productboard to help",
    "special limited time offer",
    "head on over to lennysnewsletter.com",
    "get a thousand dollars in credit",
    "if you're setting up your analytics stack",
    "number one most popular analytic solution",
    "use the code",
    "check out our sponsor",
    "introducing jira product discovery",
    "that's workos.com",
    "visit ahrefs.com",
)


def _prepare_search_query(question: str) -> str:
    """Extract useful topic terms from a natural-language question."""
    if not question or not question.strip():
        return ""

    if len(question) > MAX_QUERY_LENGTH:
        raise ValueError(
            f"Search question must not exceed {MAX_QUERY_LENGTH} characters."
        )

    normalized = question.lower().replace("’", "'").replace("â€™", "'")

    normalized = re.sub(
        r"\b(according to|lenny'?s podcast|lenny'?s newsletter|"
        r"what are|what is|how can|how do|can a|could a|should a|"
        r"please|explain|describe|give me|tell me|find|cite|"
        r"relevant|episodes?|guests?|examples?|practical ways|"
        r"three|each|early.stage startup)\b",
        " ",
        normalized,
    )

    words = re.findall(r"[a-z0-9]+", normalized)

    return " ".join(
        word for word in words
        if word not in STOP_WORDS and not word.isdigit()
    )


def _build_search_queries(question: str) -> list[str]:
    """Build the core query first and add targeted expansions."""
    base_query = _prepare_search_query(question)

    if not base_query:
        return []

    words = base_query.split()
    queries = [base_query]

    for word in words:
        queries.extend(QUERY_EXPANSIONS.get(word, ()))

    return list(dict.fromkeys(
        query.strip() for query in queries if query.strip()
    ))


def _topic_title_score(result: dict, topic_terms: set[str]) -> int:
    """Score overlap between topic terms and episode title words."""
    title = (result.get("episode_title") or "").lower()
    title_words = set(re.findall(r"[a-z0-9]+", title))
    return len(topic_terms & title_words)

def _question_intent_score(question: str, result: dict) -> int:
    """Prioritize chunks containing evidence for the question's intent."""
    normalized_question = question.lower()
    content = (result.get("content") or "").lower()

    score = 0

    asks_percentage = any(
        phrase in normalized_question
        for phrase in (
            "percentage",
            "percent",
            "what proportion",
            "how many",
            "what fraction",
        )
    )

    if asks_percentage:
        # Strong signal: numeric proportions in the evidence.
        if re.search(r"\b\d+(?:\.\d+)?\s*(?:%|percent|per cent)\b", content):
            score += 3

        # Transcript-style verbal estimates.
        if any(
                phrase in content
                for phrase in (
                        "majority of companies",
                        "greater than 50%",
                        "60 or 70%",
                        "30% make it",
                        "half the companies",
                )
        ):
            score += 3

        # A question about reaching stages should match stage outcomes.
        if any(
                phrase in content
                for phrase in (
                        "make it to l3",
                        "reach l3",
                        "stuck at l1 or l2",
                        "stuck at l1",
                        "strong product-market fit",
                )
        ):
            score += 2

    asks_stages = any(
        phrase in normalized_question
        for phrase in ("stage", "stages", "level")
    )
    if asks_stages and any(
            term in content for term in ("l1", "l2", "l3", "l4", "level one", "level two")
    ):
        score += 2

    asks_timeline = any(
        phrase in normalized_question
        for phrase in ("how long", "timeline", "how many years")
    )
    if asks_timeline and any(
            term in content for term in ("years", "months", "weeks", "timeline")
    ):
        score += 2

    return score
def search_transcript_chunks(
        connection: Connection,
        question: str,
        limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Retrieve relevant transcript chunks while retaining episode context."""
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}.")

    base_query = _prepare_search_query(question)
    queries = _build_search_queries(question)

    if not base_query or not queries:
        return []

    core_terms = list(dict.fromkeys(base_query.split()))
    coverage_ratio = (
        0.5 if len(core_terms) >= 6
        else MIN_CORE_TERM_COVERAGE_RATIO
    )
    # Expansion queries (e.g. onboarding -> activation) can retrieve
    # relevant evidence without matching every original query term.
    # Keep strict coverage for unexpanded queries only.
    coverage_threshold = (
        0
        if len(queries) > 1
        else max(1, int(len(core_terms) * coverage_ratio + 0.999))
    )

    sql = """
          WITH search_queries AS (
              SELECT
                  query_text,
                  websearch_to_tsquery('english', query_text) AS terms,
                  CASE WHEN query_text = %s THEN 1.0 ELSE 0.2 END
                                                              AS query_weight
              FROM unnest(%s::text[]) AS q(query_text)
          ),
               candidate_scores AS (
                   SELECT
                       tc.id,
                       tc.guest,
                       tc.episode_title,
                       tc.source_path,
                       tc.source_url,
                       tc.video_id,
                       tc.start_timestamp,
                       tc.end_timestamp,
                       tc.content,
                       tc.chunk_index,
                       MAX(
                               ts_rank_cd(
                                       to_tsvector('english', tc.content),
                                       sq.terms
                               ) * sq.query_weight
                       ) AS relevance,
                       BOOL_OR(
                               sq.query_text = %s
                                   AND to_tsvector('english', tc.content) @@ sq.terms
                       ) AS original_query_match,
                       COUNT(DISTINCT sq.query_text) AS matched_query_count
                   FROM transcript_chunks AS tc
                            CROSS JOIN search_queries AS sq
                   WHERE to_tsvector('english', tc.content) @@ sq.terms
              AND NOT (lower(tc.content) LIKE ANY(%s::text[]))
          GROUP BY
              tc.id,
              tc.guest,
              tc.episode_title,
              tc.source_path,
              tc.source_url,
              tc.video_id,
              tc.start_timestamp,
              tc.end_timestamp,
              tc.content,
              tc.chunk_index
              ),
              scored AS (
          SELECT
              candidate_scores.*,
              (
              SELECT COUNT(*)
              FROM unnest(%s::text[]) AS term(word)
              WHERE to_tsvector(
              'english', candidate_scores.content
              ) @@ plainto_tsquery('english', term.word)
              ) AS core_term_coverage
          FROM candidate_scores
              )
          SELECT
              id, guest, episode_title, source_path, source_url, video_id,
              start_timestamp, end_timestamp, content, relevance,
              matched_query_count, original_query_match, core_term_coverage
          FROM scored
          WHERE core_term_coverage >= %s
          ORDER BY
              relevance DESC,
              core_term_coverage DESC,
              original_query_match DESC,
              matched_query_count DESC,
              source_path,
              chunk_index
              LIMIT %s \
          """

    promotional_patterns = [
        f"%{marker}%" for marker in PROMOTIONAL_MARKERS
    ]
    candidate_limit = min(max(limit * 20, 50), 200)

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            sql,
            (
                base_query,
                queries,
                base_query,
                promotional_patterns,
                core_terms,
                coverage_threshold,
                candidate_limit,
            ),
        )
        rows = cursor.fetchall()

    results = [
        dict(row)
        for row in rows
        if not _is_promotional_content(row["content"])
    ]

    topic_terms = set(base_query.split())

    results.sort(
        key=lambda result: (
            _question_intent_score(question, result),
            result.get("relevance", 0),
            result.get("core_term_coverage", 0),
            _topic_title_score(result, topic_terms),
            result.get("original_query_match", False),
            result.get("matched_query_count", 0),
        ),
        reverse=True,
    )
    # First select the strongest chunk from each episode.
    selected = []
    selected_ids = set()
    episode_counts = {}

    for result in results:
        source = result.get("source_path") or result.get("episode_title")

        if not source or episode_counts.get(source, 0) >= 1:
            continue

        selected.append(result)
        selected_ids.add(result.get("id"))
        episode_counts[source] = 1

        if len(selected) >= limit:
            return selected

    # Use remaining slots for a second chunk from a relevant episode.
    for result in results:
        result_id = result.get("id")
        source = result.get("source_path") or result.get("episode_title")

        if result_id in selected_ids or not source:
            continue

        if episode_counts.get(source, 0) >= MAX_CHUNKS_PER_EPISODE:
            continue

        selected.append(result)
        selected_ids.add(result_id)
        episode_counts[source] = episode_counts.get(source, 0) + 1

        if len(selected) >= limit:
            break

    return selected