
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from psycopg import Error as PsycopgError

from app.db.session import get_db_connection

router = APIRouter(prefix="/api/v1/sessions", tags=["Sessions"])


class SessionCreate(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=200)
    user_id: str | None = Field(default=None, max_length=200)


class SessionResponse(BaseModel):
    id: UUID
    title: str
    user_id: str | None
    created_at: str
    updated_at: str


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionCreate) -> dict:
    session_id = uuid4()

    try:
        generator = get_db_connection()
        connection = next(generator)
        try:
            row = connection.execute(
                """
                INSERT INTO chat_sessions (id, title, user_id)
                VALUES (%s, %s, %s)
                    RETURNING id, title, user_id, created_at, updated_at
                """,
                (session_id, payload.title, payload.user_id),
            ).fetchone()
            connection.commit()
        finally:
            generator.close()
    except PsycopgError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc

    return {
        "id": row[0],
        "title": row[1],
        "user_id": row[2],
        "created_at": row[3].isoformat(),
        "updated_at": row[4].isoformat(),
    }


@router.get("", response_model=list[SessionResponse])
def list_sessions() -> list[dict]:
    try:
        generator = get_db_connection()
        connection = next(generator)
        try:
            rows = connection.execute(
                """
                SELECT id, title, user_id, created_at, updated_at
                FROM chat_sessions
                ORDER BY updated_at DESC
                """
            ).fetchall()
        finally:
            generator.close()
    except PsycopgError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc

    return [
        {
            "id": row[0],
            "title": row[1],
            "user_id": row[2],
            "created_at": row[3].isoformat(),
            "updated_at": row[4].isoformat(),
        }
        for row in rows
    ]