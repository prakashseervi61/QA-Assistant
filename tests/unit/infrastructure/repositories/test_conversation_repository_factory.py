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
from src.infrastructure.repositories.sqlite_conversation_repository import (
    SQLiteConversationRepository,
)

DB_URL = "postgresql+asyncpg://user:pass@localhost:5432/db"


def _settings(database_url=None, history_path="./data/history.db"):
    """Build a settings stub with the attributes the factory reads.

    ``history_path`` must always be a real string. A bare MagicMock would hand
    the real SQLite repository a mock's repr as its path and create a
    directory named after it.
    """
    assert history_path is None or isinstance(history_path, str), (
        "history_path must be a str or None, got "
        f"{type(history_path).__name__}"
    )
    settings = MagicMock()
    settings.DATABASE_URL = database_url
    settings.HISTORY_DB_PATH = history_path
    return settings


class TestConversationRepositoryFactory:
    def test_factory_returns_sqlite_when_no_db_url(self, tmp_path):
        """No DATABASE_URL -> SQLite, so history survives a restart."""
        with patch(
            "src.infrastructure.repositories.conversation_repository_factory.get_settings"
        ) as mock_settings:
            mock_settings.return_value = _settings(
                history_path=str(tmp_path / "history.db")
            )

            repo = create_conversation_repository()
            assert isinstance(repo, SQLiteConversationRepository)

    def test_factory_uses_configured_history_path(self, tmp_path):
        """HISTORY_DB_PATH is honoured, including its parent directory."""
        db = tmp_path / "nested" / "custom.db"
        with patch(
            "src.infrastructure.repositories.conversation_repository_factory.get_settings"
        ) as mock_settings:
            mock_settings.return_value = _settings(history_path=str(db))

            repo = create_conversation_repository()

        assert isinstance(repo, SQLiteConversationRepository)
        assert db.parent.is_dir()

    def test_factory_falls_back_to_memory_when_history_path_unusable(self):
        """A history path that cannot be opened degrades to in-memory."""
        with (
            patch(
                "src.infrastructure.repositories.conversation_repository_factory.get_settings"
            ) as mock_settings,
            patch(
                "src.infrastructure.repositories.conversation_repository_factory.SQLiteConversationRepository",
                side_effect=OSError("read-only file system"),
            ),
        ):
            mock_settings.return_value = _settings()

            repo = create_conversation_repository()
            assert isinstance(repo, MemoryConversationRepository)

    def test_factory_returns_memory_when_no_history_path_configured(self):
        """An empty HISTORY_DB_PATH skips SQLite entirely."""
        with patch(
            "src.infrastructure.repositories.conversation_repository_factory.get_settings"
        ) as mock_settings:
            mock_settings.return_value = _settings(history_path=None)

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
            settings = _settings(database_url=DB_URL)
            mock_settings.return_value = settings
            mock_postgres.return_value = MagicMock()

            repo = create_conversation_repository()
            mock_postgres.assert_called_once_with(settings.DATABASE_URL)
            assert repo is mock_postgres.return_value

    def test_factory_falls_back_to_sqlite_when_postgres_unreachable(self, tmp_path):
        """DATABASE_URL set but probe fails -> SQLite history instead."""
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
            mock_settings.return_value = _settings(
                database_url=DB_URL, history_path=str(tmp_path / "history.db")
            )
            mock_postgres.return_value = MagicMock()

            repo = create_conversation_repository()
            assert isinstance(repo, SQLiteConversationRepository)

    def test_factory_falls_back_to_sqlite_on_postgres_error(self, tmp_path):
        """Postgres construction failure -> SQLite history, no crash."""
        with (
            patch(
                "src.infrastructure.repositories.conversation_repository_factory.get_settings"
            ) as mock_settings,
            patch(
                "src.infrastructure.repositories.conversation_repository_factory.PostgresConversationRepository",
                side_effect=ImportError("no sqlalchemy"),
            ),
        ):
            mock_settings.return_value = _settings(
                database_url=DB_URL, history_path=str(tmp_path / "history.db")
            )

            repo = create_conversation_repository()
            assert isinstance(repo, SQLiteConversationRepository)


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
