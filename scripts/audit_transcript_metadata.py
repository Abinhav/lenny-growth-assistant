
from collections import defaultdict
from pathlib import Path

import yaml


TRANSCRIPT_ROOT = Path("data/lennys-podcast-transcripts/episodes")


def read_metadata(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")

    if not text.startswith("---"):
        return {}

    parts = text.split("---", 2)
    if len(parts) != 3:
        return {}

    try:
        metadata = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}

    return metadata if isinstance(metadata, dict) else {}


def main() -> None:
    if not TRANSCRIPT_ROOT.exists():
        raise SystemExit(
            f"Transcript directory not found: {TRANSCRIPT_ROOT}"
        )

    by_video_id = defaultdict(list)
    by_source_url = defaultdict(list)
    total_files = 0
    missing_metadata = []

    for path in sorted(TRANSCRIPT_ROOT.rglob("transcript.md")):
        total_files += 1
        metadata = read_metadata(path)

        guest = str(metadata.get("guest") or "").strip()
        title = str(metadata.get("title") or "").strip()
        video_id = str(metadata.get("video_id") or "").strip()
        source_url = str(metadata.get("youtube_url") or "").strip()

        record = {
            "path": path.relative_to(TRANSCRIPT_ROOT).as_posix(),
            "guest": guest,
            "title": title,
            "video_id": video_id,
            "source_url": source_url,
        }

        if not guest or not title or not video_id or not source_url:
            missing_metadata.append(record)

        if video_id:
            by_video_id[video_id].append(record)

        if source_url:
            by_source_url[source_url].append(record)

    duplicate_video_ids = {
        key: records
        for key, records in by_video_id.items()
        if len(records) > 1
    }
    duplicate_urls = {
        key: records
        for key, records in by_source_url.items()
        if len(records) > 1
    }

    print(f"Transcript files scanned: {total_files}")
    print(f"Duplicate video IDs: {len(duplicate_video_ids)}")
    print(f"Duplicate source URLs: {len(duplicate_urls)}")
    print(f"Files with missing metadata: {len(missing_metadata)}")

    for video_id, records in sorted(duplicate_video_ids.items()):
        print(f"\nDUPLICATE VIDEO ID: {video_id}")
        for record in records:
            print(
                f"  {record['path']} | guest={record['guest']} "
                f"| title={record['title']}"
            )

    if missing_metadata:
        print("\nMISSING METADATA")
        for record in missing_metadata:
            print(f"  {record['path']} | {record}")


if __name__ == "__main__":
    main()

