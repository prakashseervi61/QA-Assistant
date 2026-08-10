"""Unit tests for the Postgres conversation repository (mocked engine).

These tests never touch a real database: the sqlalchemy async engine and
text() helper are mocked, so the suite runs without sqlalchemy installed.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message
from src.domain.interfaces.conversation_repository import ConversationRepository
from src.infrastructure.repositories.postgres_conversation_repository import (
    PostgresConversationRepository,
    PostgresUnavailableError,
)

DB_URL = "postgresql+asyncpg://user:pass@localhost:5432/qa_assistant"


def make_result(rows=None, one=None):
    """Build a mock query result with scripted fetchall/fetchone."""
    result = MagicMock()
    result.fetchall = AsyncMock(return_value=rows if rows is not None else [])
    result.fetchone = AsyncMock(return_value=one)
    return result


class FakeRow:
    """Row-like object exposing a ``_mapping`` (as SQLAlchemy Row does)."""

    def __init__(self, **values):
        self._mapping = values


class FakeConnection:
    """Async context manager connection with scripted execute results."""

    def __init__(self, results=None):
        self.results = list(results or [])
        self.executed = []
        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        if self.results:
            return self.results.pop(0)
        return make_result()


@pytest.fixture
def repo_and_engine():
    """Construct the Postgres repo with a mocked async engine."""
    with patch(
        "src.infrastructure.repositories.postgres_conversation_repository._load_sqlalchemy"
    ) as mock_load:
        mock_engine = MagicMock()
        mock_load.return_value = (
            lambda sql: sql,
            MagicMock(return_value=mock_engine),
        )
        repo = PostgresConversationRepository(DB_URL)
        repo._schema_ready = True  # skip schema DDL in method tests
        yield repo, mock_engine


class TestPostgresConversationRepository:
    def test_implements_conversation_repository_interface(self, repo_and_engine):
        repo, _ = repo_and_engine
        assert isinstance(repo, ConversationRepository)

    def test_constructor_normalizes_bare_postgres_url(self):
        with patch(
            "src.infrastructure.repositories.postgres_conversation_repository._load_sqlalchemy"
        ) as mock_load:
            mock_create = MagicMock()
            mock_load.return_value = (lambda sql: sql, mock_create)
            PostgresConversationRepository("postgresql://user:pass@localhost/db")
            mock_create.assert_called_once_with(
                "postgresql+asyncpg://user:pass@localhost/db", echo=False
            )

    def test_constructor_raises_when_sqlalchemy_unavailable(self):
        with patch(
            "src.infrastructure.repositories.postgres_conversation_repository._load_sqlalchemy",
            side_effect=ImportError("no module named sqlalchemy"),
        ):
            with pytest.raises(PostgresUnavailableError):
                PostgresConversationRepository(DB_URL)

    def test_constructor_raises_when_engine_creation_fails(self):
        with patch(
            "src.infrastructure.repositories.postgres_conversation_repository._load_sqlalchemy"
        ) as mock_load:

            def failing_factory(url, echo=False):
                raise RuntimeError("invalid DSN")

            mock_load.return_value = (lambda sql: sql, failing_factory)
            with pytest.raises(PostgresUnavailableError):
                PostgresConversationRepository("not a url")

    @pytest.mark.asyncio
    async def test_ensure_schema_applies_idempotent_schema(self, repo_and_engine):
        repo, mock_engine = repo_and_engine
        repo._schema_ready = False
        conn = FakeConnection()
        mock_engine.connect.return_value = conn

        await repo._ensure_schema()

        statements = " ".join(sql for sql, _ in conn.executed)
        assert "CREATE TABLE IF NOT EXISTS conversations" in statements
        assert "CREATE TABLE IF NOT EXISTS messages" in statements
        assert "CREATE INDEX IF NOT EXISTS idx_messages_conversation" in statements
        assert repo._schema_ready is True

    @pytest.mark.asyncio
    async def test_ensure_schema_raises_when_connection_fails(self, repo_and_engine):
        repo, mock_engine = repo_and_engine
        repo._schema_ready = False
        conn = FakeConnection()
        conn.execute = AsyncMock(side_effect=RuntimeError("connection refused"))
        mock_engine.connect.return_value = conn

        with pytest.raises(PostgresUnavailableError):
            await repo._ensure_schema()

        assert repo._schema_ready is False

    @pytest.mark.asyncio
    async def test_save_conversation_upserts_and_syncs_messages(self, repo_and_engine):
        repo, mock_engine = repo_and_engine
        conn = FakeConnection()
        mock_engine.connect.return_value = conn
        message = Message(role="user", content="hello")
        conversation = Conversation(
            id=uuid4(),
            title="Test",
            messages=[message],
            document_ids=[uuid4()],
        )

        await repo.save_conversation(conversation)

        sqls = [sql for sql, _ in conn.executed]
        assert len(sqls) == 3  # upsert conversation + delete + insert messages
        assert any("INSERT INTO conversations" in sql for sql in sqls)
        assert any("DELETE FROM messages" in sql for sql in sqls)
        assert any("INSERT INTO messages" in sql for sql in sqls)
        assert conn.commit.await_count == 1

    @pytest.mark.asyncio
    async def test_save_conversation_binds_tz_aware_timestamps(self, repo_and_engine):
        """Timestamps bound for TIMESTAMPTZ columns are tz-aware UTC."""
        repo, mock_engine = repo_and_engine
        conn = FakeConnection()
        mock_engine.connect.return_value = conn
        conversation = Conversation(
            id=uuid4(),
            title="Test",
            messages=[Message(role="user", content="hello")],
            document_ids=[uuid4()],
            updated_at=None,  # naive entity default -> repo fallback
        )

        await repo.save_conversation(conversation)

        upsert_params = None
        message_params = None
        for sql, params in conn.executed:
            if "INSERT INTO conversations" in str(sql):
                upsert_params = params
            elif "INSERT INTO messages" in str(sql):
                message_params = params
        assert upsert_params is not None
        assert message_params is not None
        # Every timestamp bound to a TIMESTAMPTZ column is tz-aware.
        assert upsert_params["created_at"].tzinfo is not None
        assert upsert_params["updated_at"].tzinfo is not None
        assert message_params["created_at"].tzinfo is not None

    @pytest.mark.asyncio
    async def test_add_message_binds_tz_aware_created_at(self, repo_and_engine):
        """add_message() normalizes naive message timestamps to UTC."""
        repo, mock_engine = repo_and_engine
        conv_id = uuid4()
        conn = FakeConnection(
            results=[
                make_result(one=FakeRow(id=conv_id)),  # exists check
                make_result(),  # INSERT
                make_result(),  # UPDATE
            ]
        )
        mock_engine.connect.return_value = conn

        await repo.add_message(conv_id, Message(role="assistant", content="answer"))

        insert_params = None
        for sql, params in conn.executed:
            if "INSERT INTO messages" in str(sql):
                insert_params = params
        assert insert_params is not None
        assert insert_params["created_at"].tzinfo is not None

    @pytest.mark.asyncio
    async def test_get_conversation_returns_entity_with_messages(self, repo_and_engine):
        repo, mock_engine = repo_and_engine
        conv_id = uuid4()
        now = datetime.now()
        doc_id = "11111111-1111-1111-1111-111111111111"
        conversation_row = FakeRow(
            id=conv_id,
            title="Test conversation",
            document_ids=[doc_id],
            created_at=now,
            updated_at=now,
        )
        message_row = FakeRow(
            id=uuid4(),
            role="user",
            content="Hello",
            sources=[{"document_id": doc_id}],
            created_at=now,
        )
        conn = FakeConnection(
            results=[
                make_result(one=conversation_row),
                make_result(rows=[message_row]),
            ]
        )
        mock_engine.connect.return_value = conn

        conversation = await repo.get_conversation(conv_id)

        assert conversation.id == conv_id
        assert conversation.title == "Test conversation"
        assert conversation.document_ids == [UUID(doc_id)]
        assert len(conversation.messages) == 1
        assert conversation.messages[0].role == "user"
        assert conversation.messages[0].content == "Hello"
        assert conversation.messages[0].sources == [{"document_id": doc_id}]

    @pytest.mark.asyncio
    async def test_get_conversation_missing_raises_key_error(self, repo_and_engine):
        repo, mock_engine = repo_and_engine
        conn = FakeConnection(results=[make_result(one=None)])
        mock_engine.connect.return_value = conn

        with pytest.raises(KeyError):
            await repo.get_conversation(uuid4())

    @pytest.mark.asyncio
    async def test_list_conversations_returns_with_messages(self, repo_and_engine):
        repo, mock_engine = repo_and_engine
        first_id, second_id = uuid4(), uuid4()
        now = datetime.now()
        conversation_rows = [
            FakeRow(
                id=first_id,
                title="First",
                document_ids=[],
                created_at=now,
                updated_at=now,
            ),
            FakeRow(
                id=second_id,
                title="Second",
                document_ids=[],
                created_at=now,
                updated_at=now,
            ),
        ]
        message_rows = [
            FakeRow(
                id=uuid4(),
                conversation_id=second_id,
                role="user",
                content="question two",
                sources=[],
                created_at=now,
            ),
            FakeRow(
                id=uuid4(),
                conversation_id=first_id,
                role="assistant",
                content="answer one",
                sources=[],
                created_at=now,
            ),
        ]
        conn = FakeConnection(
            results=[
                make_result(rows=conversation_rows),
                make_result(rows=message_rows),
            ]
        )
        mock_engine.connect.return_value = conn

        conversations = await repo.list_conversations(limit=10)

        assert [c.id for c in conversations] == [first_id, second_id]
        assert [m.content for m in conversations[0].messages] == ["answer one"]
        assert [m.content for m in conversations[1].messages] == ["question two"]

    @pytest.mark.asyncio
    async def test_add_message_inserts_and_updates_conversation(self, repo_and_engine):
        repo, mock_engine = repo_and_engine
        conv_id = uuid4()
        conn = FakeConnection(
            results=[
                make_result(one=FakeRow(id=conv_id)),  # exists check
                make_result(),  # INSERT
                make_result(),  # UPDATE
            ]
        )
        mock_engine.connect.return_value = conn

        await repo.add_message(conv_id, Message(role="assistant", content="answer"))

        sqls = [sql for sql, _ in conn.executed]
        assert any("INSERT INTO messages" in sql for sql in sqls)
        assert any("UPDATE conversations" in sql for sql in sqls)
        assert conn.commit.await_count == 1

    @pytest.mark.asyncio
    async def test_add_message_raises_key_error_when_conversation_missing(
        self, repo_and_engine
    ):
        repo, mock_engine = repo_and_engine
        conn = FakeConnection(results=[make_result(one=None)])
        mock_engine.connect.return_value = conn

        with pytest.raises(KeyError):
            await repo.add_message(uuid4(), Message(role="user", content="hi"))

    @pytest.mark.asyncio
    async def test_get_messages_returns_chronological(self, repo_and_engine):
        repo, mock_engine = repo_and_engine
        conv_id = uuid4()
        now = datetime.now()
        message_row = FakeRow(
            id=uuid4(),
            role="user",
            content="Hello",
            sources=[],
            created_at=now,
        )
        conn = FakeConnection(
            results=[
                make_result(one=FakeRow(id=conv_id)),
                make_result(rows=[message_row]),
            ]
        )
        mock_engine.connect.return_value = conn

        messages = await repo.get_messages(conv_id)

        assert len(messages) == 1
        assert messages[0].content == "Hello"

    @pytest.mark.asyncio
    async def test_get_messages_raises_key_error_when_missing(self, repo_and_engine):
        repo, mock_engine = repo_and_engine
        conn = FakeConnection(results=[make_result(one=None)])
        mock_engine.connect.return_value = conn

        with pytest.raises(KeyError):
            await repo.get_messages(uuid4())

    @pytest.mark.asyncio
    async def test_delete_conversation_returns_true(self, repo_and_engine):
        repo, mock_engine = repo_and_engine
        conv_id = uuid4()
        conn = FakeConnection(results=[make_result(one=FakeRow(id=conv_id))])
        mock_engine.connect.return_value = conn

        deleted = await repo.delete_conversation(conv_id)

        assert deleted is True
        assert conn.commit.await_count == 1

    @pytest.mark.asyncio
    async def test_delete_conversation_missing_returns_false(self, repo_and_engine):
        repo, mock_engine = repo_and_engine
        conn = FakeConnection(results=[make_result(one=None)])
        mock_engine.connect.return_value = conn

        assert await repo.delete_conversation(uuid4()) is False

    @pytest.mark.asyncio
    async def test_conversation_exists(self, repo_and_engine):
        repo, mock_engine = repo_and_engine
        conv_id = uuid4()
        conn = FakeConnection(results=[make_result(one=FakeRow(id=conv_id))])
        mock_engine.connect.return_value = conn

        assert await repo.conversation_exists(conv_id) is True

    @pytest.mark.asyncio
    async def test_conversation_exists_false_when_missing(self, repo_and_engine):
        repo, mock_engine = repo_and_engine
        conn = FakeConnection(results=[make_result(one=None)])
        mock_engine.connect.return_value = conn

        assert await repo.conversation_exists(uuid4()) is False
