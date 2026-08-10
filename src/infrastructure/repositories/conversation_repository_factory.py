"""Conversation repository factory: Postgres when configured, in-memory otherwise."""

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

    Returns a Postgres-backed repository when ``DATABASE_URL`` is set, the
    optional sqlalchemy dependency is available, and the database answers
    a connectivity probe; otherwise falls back to the in-memory
    repository. Never raises.
    """
    settings = get_settings()
    database_url = getattr(settings, "DATABASE_URL", None)
    if not database_url:
        return MemoryConversationRepository()

    try:
        repo = PostgresConversationRepository(database_url)
    except Exception as exc:
        logger.warning(
            "Postgres conversation repository unavailable (%s); "
            "falling back to in-memory",
            exc,
        )
        return MemoryConversationRepository()

    if not probe_postgres_connectivity(repo):
        logger.warning(
            "Postgres conversation repository is configured but unreachable; "
            "falling back to in-memory storage"
        )
        return MemoryConversationRepository()

    logger.info("Using Postgres conversation repository")
    return repo
