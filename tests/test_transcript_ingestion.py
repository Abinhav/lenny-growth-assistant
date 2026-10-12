
from pathlib import Path

from app.services.transcript_ingestion import (
    _is_promotional_content,
    _split_frontmatter,
    _split_text,
    parse_transcript_file,
)


def test_split_frontmatter_reads_metadata() -> None:
    text = (
        '---\nguest: "Example Guest"\ntitle: "Example Episode"\n---\n'
        "# Example Episode\n\nTranscript text."
    )

    metadata, body = _split_frontmatter(text)

    assert metadata["guest"] == "Example Guest"
    assert metadata["title"] == "Example Episode"
    assert "Transcript text." in body


def test_split_frontmatter_handles_missing_frontmatter() -> None:
    metadata, body = _split_frontmatter("Plain transcript text.")

    assert metadata == {}
    assert body == "Plain transcript text."


def test_split_text_creates_overlapping_chunks() -> None:
    text = "A" * 100 + "\n\n" + "B" * 100

    chunks = _split_text(text, chunk_size=120, overlap=20)

    assert len(chunks) >= 2
    assert all(chunks)
    assert "".join(chunks).count("B") >= 100


def test_parse_transcript_file_preserves_source_identity(
        tmp_path: Path,
) -> None:
    transcript_root = tmp_path / "episodes"
    episode_dir = transcript_root / "example-guest"
    episode_dir.mkdir(parents=True)

    transcript_file = episode_dir / "transcript.md"
    transcript_file.write_text(
        '---\n'
        'guest: "Example Guest"\n'
        'title: "Example Episode"\n'
        'youtube_url: "https://example.com/video"\n'
        'video_id: "example123"\n'
        '---\n'
        '# Example Episode\n\n'
        '## Transcript\n\n'
        'Example Guest (00:00:01): This is the first sentence.\n\n'
        'Lenny Rachitsky (00:00:05): This is the second sentence.\n',
        encoding="utf-8",
    )

    chunks = parse_transcript_file(
        transcript_file,
        transcript_root=transcript_root,
    )

    assert chunks
    assert chunks[0].source_path == "example-guest/transcript.md"
    assert chunks[0].guest == "Example Guest"
    assert chunks[0].episode_title == "Example Episode"
    assert chunks[0].source_url == "https://example.com/video"
    assert chunks[0].video_id == "example123"
    assert chunks[0].start_timestamp == "00:00:01"
    assert chunks[0].content_hash


def test_parse_transcript_file_handles_missing_optional_metadata(
        tmp_path: Path,
) -> None:
    transcript_root = tmp_path / "episodes"
    episode_dir = transcript_root / "guest-without-url"
    episode_dir.mkdir(parents=True)

    transcript_file = episode_dir / "transcript.md"
    transcript_file.write_text(
        '---\n'
        'guest: "Guest Without URL"\n'
        '---\n'
        '# Guest Without URL\n\n'
        '## Transcript\n\n'
        'Guest Without URL (00:00:02): Useful transcript content.\n',
        encoding="utf-8",
    )

    chunks = parse_transcript_file(
        transcript_file,
        transcript_root=transcript_root,
    )

    assert chunks
    assert chunks[0].guest == "Guest Without URL"
    assert chunks[0].source_url is None
    assert chunks[0].video_id is None
    assert chunks[0].source_path == "guest-without-url/transcript.md"


def test_promotional_content_detects_sponsor_read() -> None:
    content = (
        "This episode is brought to you by ExampleCo. "
        "Visit example.com to learn more."
    )

    assert _is_promotional_content(content) is True


def test_promotional_content_detects_newsletter_ad() -> None:
    content = (
        "If you enjoy this podcast, don't forget to subscribe. "
        "Become an annual subscriber of my newsletter today."
    )

    assert _is_promotional_content(content) is True


def test_promotional_content_keeps_normal_discussion() -> None:
    content = (
        "We improved onboarding by helping users reach their "
        "first meaningful product outcome faster."
    )

    assert _is_promotional_content(content) is False
