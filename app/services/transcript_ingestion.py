
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


CHUNK_SIZE = 1800
CHUNK_OVERLAP = 250

PROMOTIONAL_MARKERS = (
    "this episode is brought to you by",
    "this episode is sponsored by",
    "this episode is supported by",
    "our sponsor",
    "today's sponsor",
    "today's episode is sponsored by",
    "if you enjoy this podcast, don't forget to subscribe",
    "become an annual subscriber of my newsletter",
    "special limited time offer",
    "check out our sponsor",
    "use the code",
    "visit ahrefs.com",
    "that's workos.com",
    "introducing jira product discovery",
    "get a thousand dollars in credit",
    "head on over to lennysnewsletter.com",
    "number one most popular analytic solution",
)


@dataclass(frozen=True)
class TranscriptChunk:
    """A searchable chunk of a transcript with source metadata."""

    source_path: str
    chunk_index: int
    guest: str
    episode_title: str
    source_url: str | None
    video_id: str | None
    start_timestamp: str | None
    end_timestamp: str | None
    content: str
    content_hash: str


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Separate YAML frontmatter from the Markdown transcript body."""
    normalized = text.lstrip("\ufeff")

    match = re.match(
        r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)",
        normalized,
        flags=re.DOTALL,
    )

    if not match:
        return {}, normalized

    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        metadata = {}

    if not isinstance(metadata, dict):
        metadata = {}

    body = normalized[match.end():]
    return metadata, body


def _is_promotional_content(content: str) -> bool:
    """Identify chunks containing obvious sponsor or promotional language."""
    normalized = " ".join(content.lower().split())
    return any(marker in normalized for marker in PROMOTIONAL_MARKERS)


def _remove_sponsor_segments(text: str) -> str:
    """Remove clearly identifiable promotional paragraphs from transcript text."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    retained: list[str] = []

    for paragraph in paragraphs:
        cleaned = paragraph.strip()
        if not cleaned:
            continue

        if _is_promotional_content(cleaned):
            continue

        retained.append(cleaned)

    return "\n\n".join(retained)


def _extract_timestamps(text: str) -> list[str]:
    """Extract timestamps from speaker-labelled transcript lines."""
    pattern = re.compile(
        r"\((\d{2}:\d{2}(?::\d{2})?)\)"
    )
    return pattern.findall(text)


def _split_text(
        text: str,
        chunk_size: int = CHUNK_SIZE,
        overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph boundaries."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between zero and chunk_size - 1.")

    normalized = text.strip()
    if not normalized:
        return []

    if len(normalized) <= chunk_size:
        return [normalized]

    chunks: list[str] = []
    start = 0
    text_length = len(normalized)

    while start < text_length:
        end = min(start + chunk_size, text_length)

        if end < text_length:
            boundary = normalized.rfind("\n\n", start, end)

            # Avoid producing very small chunks because of an early boundary.
            if boundary > start + chunk_size // 2:
                end = boundary

        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        next_start = max(0, end - overlap)

        # Prefer starting the next chunk at a paragraph boundary when possible.
        paragraph_boundary = normalized.find("\n\n", next_start, end)
        if paragraph_boundary != -1 and paragraph_boundary > start:
            next_start = paragraph_boundary + 2

        if next_start <= start:
            next_start = end

        start = next_start

    return chunks


def _metadata_value(
        metadata: dict[str, Any],
        *keys: str,
) -> str | None:
    """Return the first non-empty metadata value among candidate keys."""
    for key in keys:
        value = metadata.get(key)
        if value is not None:
            normalized = str(value).strip()
            if normalized:
                return normalized

    return None


def parse_transcript_file(
        transcript_file: Path,
        transcript_root: Path,
) -> list[TranscriptChunk]:
    """Parse a transcript Markdown file and return indexed text chunks."""
    raw_text = transcript_file.read_text(encoding="utf-8")
    metadata, body = _split_frontmatter(raw_text)

    # Remove Markdown headings without removing the transcript itself.
    body = re.sub(
        r"(?m)^\s*#{1,6}\s+",
        "",
        body,
    ).strip()

    # Keep transcript content focused by dropping obvious promotional paragraphs.
    body = _remove_sponsor_segments(body)

    if not body:
        return []

    guest = (
            _metadata_value(metadata, "guest", "guest_name", "author")
            or transcript_file.parent.name.replace("-", " ").title()
    )
    episode_title = (
            _metadata_value(metadata, "title", "episode_title")
            or transcript_file.parent.name.replace("-", " ").title()
    )
    source_url = _metadata_value(
        metadata,
        "youtube_url",
        "source_url",
        "url",
    )
    video_id = _metadata_value(metadata, "video_id", "youtube_id")

    try:
        source_path = transcript_file.resolve().relative_to(
            transcript_root.resolve()
        ).as_posix()
    except ValueError:
        source_path = transcript_file.name

    chunks = _split_text(body)
    timestamps = _extract_timestamps(body)

    parsed_chunks: list[TranscriptChunk] = []

    for chunk_index, content in enumerate(chunks):
        chunk_timestamps = _extract_timestamps(content)

        start_timestamp = (
            chunk_timestamps[0]
            if chunk_timestamps
            else None
        )
        end_timestamp = (
            chunk_timestamps[-1]
            if chunk_timestamps
            else start_timestamp
        )

        # Fall back to the transcript's timestamps if a chunk has none.
        if not chunk_timestamps and timestamps:
            start_timestamp = None
            end_timestamp = None

        content_hash = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

        parsed_chunks.append(
            TranscriptChunk(
                source_path=source_path,
                chunk_index=chunk_index,
                guest=guest,
                episode_title=episode_title,
                source_url=source_url,
                video_id=video_id,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                content=content,
                content_hash=content_hash,
            )
        )

    return parsed_chunks


def load_transcript_chunks(
        transcript_root: Path,
) -> list[TranscriptChunk]:
    """Load all transcript.md files under an episodes directory."""
    if not transcript_root.exists():
        raise FileNotFoundError(
            f"Transcript directory does not exist: {transcript_root}"
        )

    transcript_files = sorted(transcript_root.rglob("transcript.md"))
    all_chunks: list[TranscriptChunk] = []

    for transcript_file in transcript_files:
        all_chunks.extend(
            parse_transcript_file(
                transcript_file=transcript_file,
                transcript_root=transcript_root,
            )
        )

    return all_chunks
