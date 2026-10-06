"""Conversation repository factory.

One store: a local SQLite file, so history survives restarts with no database
server to run. If the file cannot be opened the error propagates rather than
silently degrading to an in-memory store whose contents vanish on the next
restart — a silent data-loss mode is worse than a loud startup failure.
"""

from src.domain.interfaces.conversation_repository import ConversationRepository
from src.infrastructure.config.settings import get_settings
from src.infrastructure.repositories.sqlite_conversation_repository import (
    SQLiteConversationRepository,
)


def create_conversation_repository() -> ConversationRepository:
    """Create the SQLite-backed conversation repository.

    Raises:
        RuntimeError: If the history file cannot be opened.
    """
    settings = get_settings()
    history_path = getattr(settings, "HISTORY_DB_PATH", None)
    if not history_path:
        raise RuntimeError(
            "HISTORY_DB_PATH is not configured; conversation history has "
            "nowhere to persist."
        )

    try:
        repo = SQLiteConversationRepository(history_path)
    except Exception as exc:
        raise RuntimeError(
            f"Could not open the conversation history store at {history_path!r}: {exc}"
        ) from exc

    return repo
