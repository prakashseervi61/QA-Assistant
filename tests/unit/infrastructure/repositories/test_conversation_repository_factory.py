"""Tests for the conversation repository factory."""

from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure.repositories.conversation_repository_factory import (
    create_conversation_repository,
)
from src.infrastructure.repositories.sqlite_conversation_repository import (
    SQLiteConversationRepository,
)


def _settings(history_path="./data/history.db"):
    """Build a settings stub with the attributes the factory reads.

    ``history_path`` must always be a real string. A bare MagicMock would hand
    the real SQLite repository a mock's repr as its path and create a
    directory named after it.
    """
    assert history_path is None or isinstance(history_path, str), (
        f"history_path must be a str or None, got {type(history_path).__name__}"
    )
    settings = MagicMock()
    settings.HISTORY_DB_PATH = history_path
    return settings


class TestConversationRepositoryFactory:
    def test_returns_sqlite(self, tmp_path):
        """History is durable by default, so the store is always SQLite."""
        db = tmp_path / "history.db"
        with patch(
            "src.infrastructure.repositories.conversation_repository_factory.get_settings"
        ) as mock_settings:
            mock_settings.return_value = _settings(str(db))

            repo = create_conversation_repository()

        assert isinstance(repo, SQLiteConversationRepository)

    def test_creates_missing_parent_directories(self, tmp_path):
        db = tmp_path / "nested" / "deeper" / "history.db"
        with patch(
            "src.infrastructure.repositories.conversation_repository_factory.get_settings"
        ) as mock_settings:
            mock_settings.return_value = _settings(str(db))

            create_conversation_repository()

        assert db.parent.is_dir()

    def test_raises_when_history_path_is_not_configured(self):
        """No silent in-memory fallback: losing history must be loud."""
        with patch(
            "src.infrastructure.repositories.conversation_repository_factory.get_settings"
        ) as mock_settings:
            mock_settings.return_value = _settings(None)

            with pytest.raises(RuntimeError, match="HISTORY_DB_PATH"):
                create_conversation_repository()

    def test_raises_when_the_store_cannot_be_opened(self):
        """A broken history file fails startup instead of quietly discarding data."""
        with (
            patch(
                "src.infrastructure.repositories.conversation_repository_factory.get_settings"
            ) as mock_settings,
            patch(
                "src.infrastructure.repositories.conversation_repository_factory.SQLiteConversationRepository",
                side_effect=OSError("read-only file system"),
            ),
        ):
            mock_settings.return_value = _settings("./data/history.db")

            with pytest.raises(RuntimeError, match="history store"):
                create_conversation_repository()