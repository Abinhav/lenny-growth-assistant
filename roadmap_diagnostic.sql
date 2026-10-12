SELECT
    episode_title,
    guest,
    source_path,
    start_timestamp,
    LEFT(content, 700) AS excerpt
FROM transcript_chunks
WHERE
    content ILIKE '%prioritiz%'
    OR content ILIKE '%roadmap%'
    OR content ILIKE '%what to build%'
    OR content ILIKE '%product strategy%'
    OR content ILIKE '%prioritize features%'
ORDER BY
    CASE
        WHEN content ILIKE '%roadmap%' THEN 1
        WHEN content ILIKE '%what to build%' THEN 2
        WHEN content ILIKE '%prioritiz%' THEN 3
        ELSE 4
    END,
    episode_title
LIMIT 12;
