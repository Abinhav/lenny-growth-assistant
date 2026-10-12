
from collections.abc import Sequence

from psycopg import Connection
from psycopg.rows import dict_row

from app.services.transcript_ingestion import TranscriptChunk


BATCH_SIZE = 500


def refresh_transcript_index(
        connection: Connection,
        chunks: Sequence[TranscriptChunk],
        batch_size: int = BATCH_SIZE,
) -> dict[str, int]:
    """Refresh indexed episodes atomically, removing their stale chunks."""
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero.")

    if not chunks:
        return {
            "processed": 0,
            "batches": 0,
            "episodes_refreshed": 0,
            "stale_chunks_deleted": 0,
        }

    # Group chunks by source path so each episode can be refreshed safely.
    chunks_by_source: dict[str, list[TranscriptChunk]] = {}
    for chunk in chunks:
        chunks_by_source.setdefault(chunk.source_path, []).append(chunk)

    processed = 0
    batches = 0
    stale_chunks_deleted = 0

    try:
        with connection.cursor() as cursor:
            for source_path, episode_chunks in chunks_by_source.items():
                # Lock existing rows for this episode within the transaction.
                cursor.execute(
                    """
                    SELECT id
                    FROM transcript_chunks
                    WHERE source_path = %s
                        FOR UPDATE;
                    """,
                    (source_path,),
                )

                # Replace this successfully parsed episode's previous chunks.
                cursor.execute(
                    """
                    DELETE FROM transcript_chunks
                    WHERE source_path = %s;
                    """,
                    (source_path,),
                )
                stale_chunks_deleted += cursor.rowcount

                for start in range(0, len(episode_chunks), batch_size):
                    batch = episode_chunks[start : start + batch_size]

                    rows = [
                        {
                            "source_path": chunk.source_path,
                            "chunk_index": chunk.chunk_index,
                            "guest": chunk.guest,
                            "episode_title": chunk.episode_title,
                            "source_url": chunk.source_url,
                            "video_id": chunk.video_id,
                            "start_timestamp": chunk.start_timestamp,
                            "end_timestamp": chunk.end_timestamp,
                            "content": chunk.content,
                            "content_hash": chunk.content_hash,
                        }
                        for chunk in batch
                    ]

                    cursor.executemany(
                        """
                        INSERT INTO transcript_chunks (
                            source_path,
                            chunk_index,
                            guest,
                            episode_title,
                            source_url,
                            video_id,
                            start_timestamp,
                            end_timestamp,
                            content,
                            content_hash
                        )
                        VALUES (
                                   %(source_path)s,
                                   %(chunk_index)s,
                                   %(guest)s,
                                   %(episode_title)s,
                                   %(source_url)s,
                                   %(video_id)s,
                                   %(start_timestamp)s,
                                   %(end_timestamp)s,
                                   %(content)s,
                                   %(content_hash)s
                               );
                        """,
                        rows,
                    )

                    processed += len(batch)
                    batches += 1

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return {
        "processed": processed,
        "batches": batches,
        "episodes_refreshed": len(chunks_by_source),
        "stale_chunks_deleted": stale_chunks_deleted,
    }


def upsert_transcript_chunks(
        connection: Connection,
        chunks: Sequence[TranscriptChunk],
        batch_size: int = BATCH_SIZE,
) -> dict[str, int]:
    """Insert or update chunks without deleting stale chunks."""
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero.")

    if not chunks:
        return {"processed": 0, "batches": 0}

    query = """
            INSERT INTO transcript_chunks (
                source_path,
                chunk_index,
                guest,
                episode_title,
                source_url,
                video_id,
                start_timestamp,
                end_timestamp,
                content,
                content_hash
            )
            VALUES (
                       %(source_path)s,
                       %(chunk_index)s,
                       %(guest)s,
                       %(episode_title)s,
                       %(source_url)s,
                       %(video_id)s,
                       %(start_timestamp)s,
                       %(end_timestamp)s,
                       %(content)s,
                       %(content_hash)s
                   )
                ON CONFLICT (source_path, chunk_index)
        DO UPDATE SET
                guest = EXCLUDED.guest,
                               episode_title = EXCLUDED.episode_title,
                               source_url = EXCLUDED.source_url,
                               video_id = EXCLUDED.video_id,
                               start_timestamp = EXCLUDED.start_timestamp,
                               end_timestamp = EXCLUDED.end_timestamp,
                               content = EXCLUDED.content,
                               content_hash = EXCLUDED.content_hash
           WHERE transcript_chunks.content_hash
                               IS DISTINCT FROM EXCLUDED.content_hash
                               OR transcript_chunks.guest
                               IS DISTINCT FROM EXCLUDED.guest
                               OR transcript_chunks.episode_title
                               IS DISTINCT FROM EXCLUDED.episode_title
                               OR transcript_chunks.source_url
                               IS DISTINCT FROM EXCLUDED.source_url
                               OR transcript_chunks.video_id
                               IS DISTINCT FROM EXCLUDED.video_id
                               OR transcript_chunks.start_timestamp
                               IS DISTINCT FROM EXCLUDED.start_timestamp
                               OR transcript_chunks.end_timestamp
                               IS DISTINCT FROM EXCLUDED.end_timestamp \
            """

    processed = 0
    batches = 0

    try:
        with connection.cursor() as cursor:
            for start in range(0, len(chunks), batch_size):
                batch = chunks[start : start + batch_size]

                rows = [
                    {
                        "source_path": chunk.source_path,
                        "chunk_index": chunk.chunk_index,
                        "guest": chunk.guest,
                        "episode_title": chunk.episode_title,
                        "source_url": chunk.source_url,
                        "video_id": chunk.video_id,
                        "start_timestamp": chunk.start_timestamp,
                        "end_timestamp": chunk.end_timestamp,
                        "content": chunk.content,
                        "content_hash": chunk.content_hash,
                    }
                    for chunk in batch
                ]

                cursor.executemany(query, rows)
                processed += len(batch)
                batches += 1

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return {"processed": processed, "batches": batches}


def get_transcript_index_stats(connection: Connection) -> dict[str, int]:
    """Return basic counts for the stored transcript index."""
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
                COUNT(*)::INTEGER AS total_chunks,
                COUNT(DISTINCT source_path)::INTEGER AS total_episodes,
                COUNT(source_url)::INTEGER AS chunks_with_source_url,
                COUNT(start_timestamp)::INTEGER AS chunks_with_timestamps
            FROM transcript_chunks;
            """
        )
        row = cursor.fetchone()

    if row is None:
        return {
            "total_chunks": 0,
            "total_episodes": 0,
            "chunks_with_source_url": 0,
            "chunks_with_timestamps": 0,
        }

    return dict(row)