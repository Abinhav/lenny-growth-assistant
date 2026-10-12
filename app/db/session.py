
from collections.abc import Generator

import psycopg

from app.core.config import get_settings


def get_db_connection() -> Generator[psycopg.Connection, None, None]:
    """Open a PostgreSQL connection and close it when finished."""
    settings = get_settings()

    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    connection = psycopg.connect(
        settings.database_url,
        connect_timeout=5,
    )

    try:
        yield connection
    finally:
        connection.close()