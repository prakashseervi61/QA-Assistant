"""Conversation repository factory.

Order of preference:
  1. Postgres  -- only when DATABASE_URL is explicitly configured
  2. SQLite    -- local file, so history survives restarts with no server
  3. In-memory -- last-resort fallback so the app always boots
"""

import asyncio
import logging

from src.domain.interfaces.conversation_repository import ConversationRepository
from src.infrastructure.config.settings import get_settings
from src.infrastructure.repositories.memory_conversation_repository import (
    MemoryConversationRepository,
)
from src.infrastructure.repositories.postgres_conversation_repository import (
    PostgresConversationRepository,
)
from src.infrastructure.repositories.sqlite_conversation_repository import (
    SQLiteConversationRepository,
)

logger = logging.getLogger(__name__)

# How long the connectivity probe may take before the database is treated
# as unreachable and the factory falls back to the in-memory repository.
_PROBE_TIMEOUT_SECONDS = 5.0


def probe_postgres_connectivity(repo: PostgresConversationRepository) -> bool:
    """Return True if *repo* can actually reach Postgres.

    The asyncpg pool is created lazily, so a configured-but-down database
    would otherwise only explode on the first request. This probe opens a
    connection, runs a trivial query, and closes it again; any failure
    (refused connection, DNS error, timeout) returns False.

    The probe runs via ``asyncio.run`` so the synchronous factory can
    verify connectivity eagerly; it must not be called from inside a
    running event loop.
    """

    async def _probe() -> None:
        async with repo._connect() as conn:
            await conn.execute(repo._text("SELECT 1"))

    try:
        asyncio.run(asyncio.wait_for(_probe(), timeout=_PROBE_TIMEOUT_SECONDS))
    except Exception:
        return False
    return True


def create_conversation_repository() -> ConversationRepository:
    """Create the appropriate conversation repository.

    Returns a Postgres-backed repository when ``DATABASE_URL`` is set and the
    database answers a connectivity probe. Otherwise a local SQLite file keeps
    history across restarts. If neither can be used the in-memory repository
    is returned so the app still boots. Never raises.
    """
    settings = get_settings()
    database_url = getattr(settings, "DATABASE_URL", None)

    if database_url:
        try:
            repo = PostgresConversationRepository(database_url)
        except Exception as exc:
            logger.warning(
                "Postgres conversation repository unavailable (%s); "
                "falling back to SQLite",
                exc,
            )
        else:
            if probe_postgres_connectivity(repo):
                logger.info("Using Postgres conversation repository")
                return repo
            logger.warning(
                "Postgres conversation repository is configured but unreachable; "
                "falling back to SQLite history storage"
            )

    history_path = getattr(settings, "HISTORY_DB_PATH", None)
    if history_path:
        try:
            sqlite_repo = SQLiteConversationRepository(history_path)
        except Exception as exc:
            logger.warning(
                "SQLite history store unavailable (%s); falling back to in-memory", exc
            )
        else:
            logger.info("Using SQLite conversation repository at %s", history_path)
            return sqlite_repo

    logger.warning(
        "No durable conversation storage available; history will not survive restarts"
    )
    return MemoryConversationRepository()
