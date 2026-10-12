
from psycopg import Connection


def create_tables(connection: Connection) -> None:
    """Create the database tables required for chat and transcript storage."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                                                         id UUID PRIMARY KEY,
                                                         title VARCHAR(200) NOT NULL DEFAULT 'New conversation',
                user_id VARCHAR(200),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                                                         id UUID PRIMARY KEY,
                                                         session_id UUID NOT NULL
                                                         REFERENCES chat_sessions(id) ON DELETE CASCADE,
                role VARCHAR(20) NOT NULL
                CHECK (role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
                ON chat_messages (session_id, created_at);
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transcript_chunks (
                                                             id BIGSERIAL PRIMARY KEY,
                                                             source_path TEXT NOT NULL,
                                                             chunk_index INTEGER NOT NULL,
                                                             guest TEXT NOT NULL,
                                                             episode_title TEXT NOT NULL,
                                                             source_url TEXT,
                                                             video_id TEXT,
                                                             start_timestamp TEXT,
                                                             end_timestamp TEXT,
                                                             content TEXT NOT NULL,
                                                             content_hash VARCHAR(64) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (source_path, chunk_index)
                );
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transcript_chunks_source
                ON transcript_chunks (source_path);
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transcript_chunks_content_fts
                ON transcript_chunks
                USING GIN (to_tsvector('english', content));
            """
        )

    connection.commit()