
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from psycopg import Error as PsycopgError

from app.db.session import get_db_connection

router = APIRouter(
    prefix="/api/v1/sessions/{session_id}/messages",
    tags=["Messages"],
)


class MessageCreate(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=50000)


class MessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    created_at: str


@router.post("", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def create_message(
        session_id: UUID,
        payload: MessageCreate,
) -> dict:
    try:
        generator = get_db_connection()
        connection = next(generator)

        try:
            session = connection.execute(
                "SELECT id FROM chat_sessions WHERE id = %s",
                (session_id,),
            ).fetchone()

            if session is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation session not found.",
                )

            message_id = uuid4()
            row = connection.execute(
                """
                INSERT INTO chat_messages (id, session_id, role, content)
                VALUES (%s, %s, %s, %s)
                    RETURNING id, session_id, role, content, created_at
                """,
                (message_id, session_id, payload.role, payload.content),
            ).fetchone()

            connection.execute(
                """
                UPDATE chat_sessions
                SET updated_at = NOW()
                WHERE id = %s
                """,
                (session_id,),
            )
            connection.commit()
        finally:
            generator.close()

    except HTTPException:
        raise
    except PsycopgError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc

    return {
        "id": row[0],
        "session_id": row[1],
        "role": row[2],
        "content": row[3],
        "created_at": row[4].isoformat(),
    }


@router.get("", response_model=list[MessageResponse])
def list_messages(session_id: UUID) -> list[dict]:
    try:
        generator = get_db_connection()
        connection = next(generator)

        try:
            session = connection.execute(
                "SELECT id FROM chat_sessions WHERE id = %s",
                (session_id,),
            ).fetchone()

            if session is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation session not found.",
                )

            rows = connection.execute(
                """
                SELECT id, session_id, role, content, created_at
                FROM chat_messages
                WHERE session_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,),
            ).fetchall()
        finally:
            generator.close()

    except HTTPException:
        raise
    except PsycopgError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc

    return [
        {
            "id": row[0],
            "session_id": row[1],
            "role": row[2],
            "content": row[3],
            "created_at": row[4].isoformat(),
        }
        for row in rows
    ]
