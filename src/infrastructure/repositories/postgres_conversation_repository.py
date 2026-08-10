"""PostgreSQL-backed conversation repository (optional persistence backend).

Used only when ``DATABASE_URL`` is configured and the optional dependencies
(sqlalchemy, asyncpg) are installed. sqlalchemy is imported lazily so this
module stays importable — and the application keeps running — without it.
The schema is applied lazily (idempotent ``CREATE TABLE IF NOT EXISTS``
statements) on first use; no alembic migration tooling is required.
"""

import functools
import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message
from src.domain.interfaces.conversation_repository import ConversationRepository

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Return the current time as a tz-aware UTC datetime.

    TIMESTAMPTZ columns require tz-aware values; naive datetimes would be
    interpreted in the server's local timezone, corrupting ordering.
    """
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Coerce *value* to a tz-aware UTC datetime (naive values are UTC).

    Entity defaults (``datetime.now()``) are naive; asyncpg rejects naive
    datetimes for TIMESTAMPTZ, so the repository normalizes every bound
    timestamp before writing.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _load_sqlalchemy():
    """Import the optional sqlalchemy bindings.

    Returns:
        A tuple of ``(text, create_async_engine)`` callables.

    Raises:
        ImportError: If sqlalchemy is not installed.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    return text, create_async_engine


# Idempotent schema. JSONB is used so document ids and message sources
# round-trip as native Python objects (asyncpg parses JSONB to dict/list).
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    document_ids JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
"""
_SCHEMA_STATEMENTS = [stmt.strip() for stmt in _SCHEMA_SQL.split(";") if stmt.strip()]


class PostgresUnavailableError(RuntimeError):
    """Raised when the Postgres repository cannot initialize or connect."""


def _log_errors(method):
    """Log and re-raise unexpected failures from repository operations.

    ``KeyError`` (conversation not found) is expected behaviour and is
    re-raised without logging.
    """

    @functools.wraps(method)
    async def wrapper(self, *args, **kwargs):
        try:
            return await method(self, *args, **kwargs)
        except KeyError:
            raise
        except Exception as exc:
            logger.error(
                "Postgres conversation repository %s failed: %s",
                method.__name__,
                exc,
            )
            raise

    return wrapper


class PostgresConversationRepository(ConversationRepository):
    """ConversationRepository backed by PostgreSQL via SQLAlchemy async."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._engine = None
        self._text_fn: Callable[[str], object] | None = None
        self._schema_ready = False
        self._init_engine()

    def _init_engine(self) -> None:
        """Build the async engine; the sqlalchemy imports are lazy."""
        if self._engine is not None:
            return
        try:
            text_fn, engine_factory = _load_sqlalchemy()
        except ImportError as exc:
            raise PostgresUnavailableError(
                'sqlalchemy is not installed; run: pip install -e ".[postgres]"'
            ) from exc
        self._text_fn = text_fn
        url = self._database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        try:
            self._engine = engine_factory(url, echo=False)
        except Exception as exc:
            raise PostgresUnavailableError(
                f"Failed to initialize Postgres engine: {exc}"
            ) from exc

    def _connect(self):
        """Open a connection on the async engine."""
        if self._engine is None:
            raise PostgresUnavailableError("Postgres engine is not initialized")
        return self._engine.connect()

    def _text(self, statement: str) -> object:
        """Build a SQL text statement (sqlalchemy.text), lazily available."""
        if self._text_fn is None:
            raise PostgresUnavailableError("sqlalchemy is not installed")
        return self._text_fn(statement)

    async def _ensure_schema(self) -> None:
        """Apply the idempotent schema once, before the first query."""
        if self._schema_ready:
            return
        try:
            async with self._connect() as conn:
                for statement in _SCHEMA_STATEMENTS:
                    await conn.execute(self._text(statement))
                await conn.commit()
            self._schema_ready = True
        except Exception as exc:
            logger.warning("Postgres schema initialization failed: %s", exc)
            raise PostgresUnavailableError(
                f"Postgres schema initialization failed: {exc}"
            ) from exc

    @_log_errors
    async def save_conversation(self, conversation: Conversation) -> None:
        """Upsert the conversation row and sync its messages."""
        await self._ensure_schema()
        now = _utcnow()
        async with self._connect() as conn:
            await conn.execute(
                self._text(
                    """
                    INSERT INTO conversations
                    (id, title, document_ids, created_at, updated_at)
                    VALUES
                    (:id, :title, CAST(:document_ids AS JSONB),
                     :created_at, :updated_at)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        document_ids = EXCLUDED.document_ids,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": conversation.id,
                    "title": conversation.title,
                    "document_ids": json.dumps(
                        [str(document_id) for document_id in conversation.document_ids]
                    ),
                    "created_at": _as_utc(conversation.created_at),
                    "updated_at": _as_utc(conversation.updated_at or now),
                },
            )
            await conn.execute(
                self._text(
                    "DELETE FROM messages WHERE conversation_id = :conversation_id"
                ),
                {"conversation_id": conversation.id},
            )
            for message in conversation.messages:
                await conn.execute(
                    self._text(
                        """
                        INSERT INTO messages
                        (id, conversation_id, role, content, sources, created_at)
                        VALUES
                        (:id, :conversation_id, :role, :content,
                         CAST(:sources AS JSONB), :created_at)
                        """
                    ),
                    {
                        "id": message.id,
                        "conversation_id": conversation.id,
                        "role": message.role,
                        "content": message.content,
                        "sources": json.dumps(message.sources),
                        "created_at": _as_utc(message.created_at),
                    },
                )
            await conn.commit()

    @_log_errors
    async def get_conversation(self, conversation_id: UUID) -> Conversation:
        """Get a conversation by ID, including its messages."""
        await self._ensure_schema()
        async with self._connect() as conn:
            result = await conn.execute(
                self._text(
                    """
                    SELECT id, title, document_ids, created_at, updated_at
                    FROM conversations
                    WHERE id = :id
                    """
                ),
                {"id": conversation_id},
            )
            row = await result.fetchone()
            if row is None:
                raise KeyError(f"Conversation not found: {conversation_id}")
            messages = await self._fetch_messages(conn, conversation_id)
            return self._row_to_conversation(row, messages)

    @_log_errors
    async def list_conversations(self, limit: int = 10) -> list[Conversation]:
        """List recent conversations (with messages), most recently updated first."""
        await self._ensure_schema()
        async with self._connect() as conn:
            result = await conn.execute(
                self._text(
                    """
                    SELECT id, title, document_ids, created_at, updated_at
                    FROM conversations
                    ORDER BY updated_at DESC NULLS LAST, created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
            rows = await result.fetchall()
            if not rows:
                return []
            conversation_ids = [row._mapping["id"] for row in rows]
            message_result = await conn.execute(
                self._text(
                    """
                    SELECT conversation_id, id, role, content, sources, created_at
                    FROM messages
                    WHERE conversation_id = ANY(:ids)
                    ORDER BY created_at, id
                    """
                ),
                {"ids": conversation_ids},
            )
            message_rows = await message_result.fetchall()
            messages_by_conversation: dict[UUID, list[Message]] = {}
            for row in message_rows:
                messages_by_conversation.setdefault(
                    row._mapping["conversation_id"], []
                ).append(self._row_to_message(row))
            return [
                self._row_to_conversation(
                    row, messages_by_conversation.get(row._mapping["id"], [])
                )
                for row in rows
            ]

    @_log_errors
    async def add_message(self, conversation_id: UUID, message: Message) -> None:
        """Add a message to a conversation and bump its updated_at."""
        await self._ensure_schema()
        async with self._connect() as conn:
            exists_result = await conn.execute(
                self._text("SELECT 1 FROM conversations WHERE id = :id"),
                {"id": conversation_id},
            )
            exists = await exists_result.fetchone()
            if exists is None:
                raise KeyError(f"Conversation not found: {conversation_id}")
            await conn.execute(
                self._text(
                    """
                    INSERT INTO messages
                    (id, conversation_id, role, content, sources, created_at)
                    VALUES
                    (:id, :conversation_id, :role, :content,
                     CAST(:sources AS JSONB), :created_at)
                    """
                ),
                {
                    "id": message.id,
                    "conversation_id": conversation_id,
                    "role": message.role,
                    "content": message.content,
                    "sources": json.dumps(message.sources),
                    "created_at": _as_utc(message.created_at),
                },
            )
            await conn.execute(
                self._text(
                    "UPDATE conversations SET updated_at = now() WHERE id = :id"
                ),
                {"id": conversation_id},
            )
            await conn.commit()

    @_log_errors
    async def get_messages(self, conversation_id: UUID) -> list[Message]:
        """Get all messages in a conversation, in chronological order."""
        await self._ensure_schema()
        async with self._connect() as conn:
            exists_result = await conn.execute(
                self._text("SELECT 1 FROM conversations WHERE id = :id"),
                {"id": conversation_id},
            )
            exists = await exists_result.fetchone()
            if exists is None:
                raise KeyError(f"Conversation not found: {conversation_id}")
            return await self._fetch_messages(conn, conversation_id)

    @_log_errors
    async def delete_conversation(self, conversation_id: UUID) -> bool:
        """Delete a conversation and its messages (FK cascade)."""
        await self._ensure_schema()
        async with self._connect() as conn:
            result = await conn.execute(
                self._text("DELETE FROM conversations WHERE id = :id RETURNING id"),
                {"id": conversation_id},
            )
            row = await result.fetchone()
            await conn.commit()
            return row is not None

    @_log_errors
    async def conversation_exists(self, conversation_id: UUID) -> bool:
        """Check whether a conversation exists."""
        await self._ensure_schema()
        async with self._connect() as conn:
            result = await conn.execute(
                self._text("SELECT 1 FROM conversations WHERE id = :id"),
                {"id": conversation_id},
            )
            row = await result.fetchone()
            return row is not None

    async def _fetch_messages(self, conn, conversation_id: UUID) -> list[Message]:
        """Load all messages for a conversation, in chronological order."""
        result = await conn.execute(
            self._text(
                """
                SELECT id, role, content, sources, created_at
                FROM messages
                WHERE conversation_id = :conversation_id
                ORDER BY created_at, id
                """
            ),
            {"conversation_id": conversation_id},
        )
        rows = await result.fetchall()
        return [self._row_to_message(row) for row in rows]

    @staticmethod
    def _row_to_message(row) -> Message:
        return Message(
            id=row._mapping["id"],
            role=row._mapping["role"],
            content=row._mapping["content"],
            sources=row._mapping["sources"],
            created_at=row._mapping["created_at"],
        )

    @staticmethod
    def _row_to_conversation(row, messages: list[Message]) -> Conversation:
        return Conversation(
            id=row._mapping["id"],
            title=row._mapping["title"],
            messages=messages,
            document_ids=[
                UUID(document_id) for document_id in row._mapping["document_ids"]
            ],
            created_at=row._mapping["created_at"],
            updated_at=row._mapping["updated_at"],
        )
