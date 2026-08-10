"""Tests for the conversation repository factory."""

from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.repositories.conversation_repository_factory import (
    create_conversation_repository,
    probe_postgres_connectivity,
)
from src.infrastructure.repositories.memory_conversation_repository import (
    MemoryConversationRepository,
)
from src.infrastructure.repositories.postgres_conversation_repository import (
    PostgresConversationRepository,
)

DB_URL = "postgresql+asyncpg://user:pass@localhost:5432/db"


class TestConversationRepositoryFactory:
    def test_factory_returns_in_memory_when_no_db_url(self):
        """No DATABASE_URL -> in-memory repository."""
        with patch(
            "src.infrastructure.repositories.conversation_repository_factory.get_settings"
        ) as mock_settings:
            settings = MagicMock()
            settings.DATABASE_URL = None
            mock_settings.return_value = settings

            repo = create_conversation_repository()
            assert isinstance(repo, MemoryConversationRepository)

    def test_factory_returns_postgres_when_db_url_set_and_reachable(self):
        """DATABASE_URL set + probe succeeds -> Postgres repository."""
        with (
            patch(
                "src.infrastructure.repositories.conversation_repository_factory.get_settings"
            ) as mock_settings,
            patch(
                "src.infrastructure.repositories.conversation_repository_factory.PostgresConversationRepository"
            ) as mock_postgres,
            patch(
                "src.infrastructure.repositories.conversation_repository_factory.probe_postgres_connectivity",
                return_value=True,
            ),
        ):
            settings = MagicMock()
            settings.DATABASE_URL = DB_URL
            mock_settings.return_value = settings
            mock_postgres.return_value = MagicMock()

            repo = create_conversation_repository()
            mock_postgres.assert_called_once_with(settings.DATABASE_URL)
            assert repo is mock_postgres.return_value

    def test_factory_falls_back_when_postgres_unreachable(self):
        """DATABASE_URL set but probe fails -> in-memory fallback."""
        with (
            patch(
                "src.infrastructure.repositories.conversation_repository_factory.get_settings"
            ) as mock_settings,
            patch(
                "src.infrastructure.repositories.conversation_repository_factory.PostgresConversationRepository"
            ) as mock_postgres,
            patch(
                "src.infrastructure.repositories.conversation_repository_factory.probe_postgres_connectivity",
                return_value=False,
            ),
        ):
            settings = MagicMock()
            settings.DATABASE_URL = DB_URL
            mock_settings.return_value = settings
            mock_postgres.return_value = MagicMock()

            repo = create_conversation_repository()
            assert isinstance(repo, MemoryConversationRepository)

    def test_factory_falls_back_on_postgres_error(self):
        """Postgres construction failure -> in-memory fallback, no crash."""
        with (
            patch(
                "src.infrastructure.repositories.conversation_repository_factory.get_settings"
            ) as mock_settings,
            patch(
                "src.infrastructure.repositories.conversation_repository_factory.PostgresConversationRepository",
                side_effect=ImportError("no sqlalchemy"),
            ),
        ):
            settings = MagicMock()
            settings.DATABASE_URL = DB_URL
            mock_settings.return_value = settings

            repo = create_conversation_repository()
            assert isinstance(repo, MemoryConversationRepository)


class TestPostgresConnectivityProbe:
    """The eager connectivity probe detects a configured-but-down DB."""

    def _build_repo(self, mock_engine) -> PostgresConversationRepository:
        with patch(
            "src.infrastructure.repositories.postgres_conversation_repository._load_sqlalchemy"
        ) as mock_load:
            mock_load.return_value = (
                lambda sql: sql,
                MagicMock(return_value=mock_engine),
            )
            return PostgresConversationRepository(DB_URL)

    def _async_conn(self) -> MagicMock:
        """Build a MagicMock usable as an async context manager for conn."""
        conn = MagicMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        return conn

    def test_probe_returns_false_when_connect_raises(self):
        """connect() raising (e.g. connection refused) -> probe fails."""
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = RuntimeError("connection refused")
        repo = self._build_repo(mock_engine)

        assert probe_postgres_connectivity(repo) is False

    def test_probe_returns_false_when_query_times_out(self):
        """A hanging connect/query is cut short by the probe timeout."""
        mock_engine = MagicMock()
        conn = self._async_conn()
        conn.execute = AsyncMock(side_effect=TimeoutError("probe timed out"))
        mock_engine.connect.return_value = conn
        repo = self._build_repo(mock_engine)

        assert probe_postgres_connectivity(repo) is False

    def test_probe_returns_true_when_connect_works(self):
        """A successful connect + trivial query -> probe passes."""
        mock_engine = MagicMock()
        conn = self._async_conn()
        conn.execute = AsyncMock()
        mock_engine.connect.return_value = conn
        repo = self._build_repo(mock_engine)

        assert probe_postgres_connectivity(repo) is True
        conn.execute.assert_called_once_with("SELECT 1")
