"""SQLite-backed conversation repository: durable history with no server.

Chosen as the default store because the app is local-first (ChromaDB is a
local directory too) and a plain file keeps chat history across restarts
without asking anyone to run a database server.

``sqlite3`` is synchronous, so every call is pushed onto a worker thread to
keep the event loop free — the same rule the rest of the infrastructure layer
follows for blocking I/O.
"""

import asyncio
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message
from src.domain.interfaces.conversation_repository import ConversationRepository

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL DEFAULT '',
    -- Legacy column: no code sets document_ids any more. Kept so existing
    -- databases keep their schema; the inserts below simply omit it.
    document_ids  TEXT NOT NULL DEFAULT '[]',
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL DEFAULT '',
    sources         TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages (conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_updated
    ON conversations (updated_at DESC);
"""


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        # A row written by an older/newer format should not take the app down.
        logger.warning("Ignoring unparseable timestamp %r", value)
        return None


def _loads_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("Ignoring unparseable JSON column")
        return []
    return parsed if isinstance(parsed, list) else []


class SQLiteConversationRepository(ConversationRepository):
    """Conversation history persisted to a local SQLite file.

    Args:
        db_path: Path to the SQLite file. Parent directories are created.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False is safe because every call below opens its
        # own short-lived connection on a worker thread.
        self._initialize()

    # ------------------------------------------------------------------
    # Connection / schema
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    async def _run(self, func, *args):
        """Run a blocking sqlite callable on a worker thread."""

        def _call():
            with self._connect() as conn:
                return func(conn, *args)

        return await asyncio.to_thread(_call)

    # ------------------------------------------------------------------
    # ConversationRepository
    # ------------------------------------------------------------------

    async def save_conversation(self, conversation: Conversation) -> None:
        updated_at = conversation.updated_at or datetime.now()

        def _write(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title      = excluded.title,
                    updated_at = excluded.updated_at
                """,
                (
                    str(conversation.id),
                    conversation.title,
                    conversation.created_at.isoformat(),
                    updated_at.isoformat(),
                ),
            )
            for message in conversation.messages:
                self._insert_message(conn, conversation.id, message)

        await self._run(_write)

    @staticmethod
    def _insert_message(
        conn: sqlite3.Connection, conversation_id: UUID, message: Message
    ) -> None:
        conn.execute(
            """
            INSERT INTO messages
                (id, conversation_id, role, content, sources, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                content    = excluded.content,
                sources    = excluded.sources,
                created_at = excluded.created_at
            """,
            (
                str(message.id),
                str(conversation_id),
                message.role,
                message.content,
                json.dumps(message.sources),
                message.created_at.isoformat(),
            ),
        )

    async def get_conversation(self, conversation_id: UUID) -> Conversation:
        def _read(conn: sqlite3.Connection) -> Conversation:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (str(conversation_id),)
            ).fetchone()
            if row is None:
                raise KeyError(f"Conversation not found: {conversation_id}")

            message_rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at",
                (str(conversation_id),),
            ).fetchall()

            messages = [
                Message(
                    id=UUID(r["id"]),
                    role=r["role"],
                    content=r["content"],
                    sources=_loads_list(r["sources"]),
                    created_at=_from_iso(r["created_at"]) or datetime.now(),
                )
                for r in message_rows
            ]
            return Conversation(
                id=UUID(row["id"]),
                title=row["title"],
                messages=messages,
                created_at=_from_iso(row["created_at"]) or datetime.now(),
                updated_at=_from_iso(row["updated_at"]),
            )

        return await self._run(_read)

    async def list_conversations(self, limit: int = 10) -> list[Conversation]:
        """List conversations, most recently updated first.

        ``limit`` may be ``None`` to return the full history, which is what
        the History view wants.
        """

        def _read(conn: sqlite3.Connection) -> list[Conversation]:
            sql = """
                SELECT c.*, COUNT(m.id) AS message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                GROUP BY c.id
                ORDER BY COALESCE(c.updated_at, c.created_at) DESC
            """
            params: tuple = ()
            if limit is not None:
                sql += " LIMIT ?"
                params = (int(limit),)
            rows = conn.execute(sql, params).fetchall()

            result: list[Conversation] = []
            for row in rows:
                message_rows = conn.execute(
                    "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at",
                    (row["id"],),
                ).fetchall()
                result.append(
                    Conversation(
                        id=UUID(row["id"]),
                        title=row["title"],
                        messages=[
                            Message(
                                id=UUID(m["id"]),
                                role=m["role"],
                                content=m["content"],
                                sources=_loads_list(m["sources"]),
                                created_at=_from_iso(m["created_at"]) or datetime.now(),
                            )
                            for m in message_rows
                        ],
                        created_at=_from_iso(row["created_at"]) or datetime.now(),
                        updated_at=_from_iso(row["updated_at"]),
                    )
                )
            return result

        return await self._run(_read)

    async def add_message(self, conversation_id: UUID, message: Message) -> None:
        def _write(conn: sqlite3.Connection) -> None:
            exists = conn.execute(
                "SELECT 1 FROM conversations WHERE id = ?", (str(conversation_id),)
            ).fetchone()
            if exists is None:
                raise KeyError(f"Conversation not found: {conversation_id}")
            self._insert_message(conn, conversation_id, message)
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), str(conversation_id)),
            )

        await self._run(_write)

    async def get_messages(self, conversation_id: UUID) -> list[Message]:
        def _read(conn: sqlite3.Connection) -> list[Message]:
            exists = conn.execute(
                "SELECT 1 FROM conversations WHERE id = ?", (str(conversation_id),)
            ).fetchone()
            if exists is None:
                raise KeyError(f"Conversation not found: {conversation_id}")
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at",
                (str(conversation_id),),
            ).fetchall()
            return [
                Message(
                    id=UUID(r["id"]),
                    role=r["role"],
                    content=r["content"],
                    sources=_loads_list(r["sources"]),
                    created_at=_from_iso(r["created_at"]) or datetime.now(),
                )
                for r in rows
            ]

        return await self._run(_read)

    async def delete_conversation(self, conversation_id: UUID) -> bool:
        def _write(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute(
                "DELETE FROM conversations WHERE id = ?", (str(conversation_id),)
            )
            # Messages go with it via ON DELETE CASCADE.
            return cursor.rowcount > 0

        return await self._run(_write)


def _is_uuid(value: object) -> bool:
    try:
        UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True
