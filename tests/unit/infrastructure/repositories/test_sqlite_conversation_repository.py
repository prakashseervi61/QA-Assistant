"""Tests for the SQLite conversation repository (durable history)."""

import pytest

from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message
from src.infrastructure.repositories.sqlite_conversation_repository import (
    SQLiteConversationRepository,
)


@pytest.fixture
def repo(tmp_path):
    return SQLiteConversationRepository(tmp_path / "history.db")


class TestSQLiteConversationRepository:
    @pytest.mark.asyncio
    async def test_save_and_get_round_trip(self, repo):
        conversation = Conversation(title="What is RAG?")
        await repo.save_conversation(conversation)

        loaded = await repo.get_conversation(conversation.id)
        assert loaded.id == conversation.id
        assert loaded.title == "What is RAG?"

    @pytest.mark.asyncio
    async def test_history_survives_a_new_repository_instance(self, tmp_path):
        """The whole point of the store: a restart must not lose history."""
        db = tmp_path / "history.db"
        first = SQLiteConversationRepository(db)
        conversation = Conversation(title="Durable")
        await first.save_conversation(conversation)

        # A brand-new instance stands in for a restarted process.
        second = SQLiteConversationRepository(db)
        assert (await second.get_conversation(conversation.id)).title == "Durable"

    @pytest.mark.asyncio
    async def test_add_message_persists_content_and_sources(self, repo):
        conversation = Conversation(title="Citations")
        await repo.save_conversation(conversation)
        await repo.add_message(
            conversation.id,
            Message(
                role="assistant",
                content="RAG grounds answers in sources.",
                sources=[{"chunk_id": "c1", "score": 0.9, "page": 3}],
            ),
        )

        messages = await repo.get_messages(conversation.id)
        assert len(messages) == 1
        assert messages[0].role == "assistant"
        assert messages[0].sources[0]["chunk_id"] == "c1"
        assert messages[0].sources[0]["page"] == 3

    @pytest.mark.asyncio
    async def test_messages_returned_in_chronological_order(self, repo):
        conversation = Conversation(title="Ordering")
        await repo.save_conversation(conversation)
        for index in range(5):
            await repo.add_message(
                conversation.id, Message(role="user", content=f"message {index}")
            )

        messages = await repo.get_messages(conversation.id)
        assert [m.content for m in messages] == [f"message {i}" for i in range(5)]

    @pytest.mark.asyncio
    async def test_get_conversation_raises_for_unknown_id(self, repo):
        from uuid import uuid4

        with pytest.raises(KeyError):
            await repo.get_conversation(uuid4())

    @pytest.mark.asyncio
    async def test_add_message_raises_for_unknown_conversation(self, repo):
        from uuid import uuid4

        with pytest.raises(KeyError):
            await repo.add_message(uuid4(), Message(role="user", content="orphan"))

    @pytest.mark.asyncio
    async def test_get_messages_raises_for_unknown_conversation(self, repo):
        from uuid import uuid4

        with pytest.raises(KeyError):
            await repo.get_messages(uuid4())

    @pytest.mark.asyncio
    async def test_missing_conversation_raises_key_error(self, repo):
        """Absence is signalled by KeyError from get_conversation.

        Replaces a test for a dedicated conversation_exists() probe that no
        production code called — the read path already reports a missing
        conversation by raising.
        """
        conversation = Conversation(title="Exists")
        with pytest.raises(KeyError):
            await repo.get_conversation(conversation.id)
        await repo.save_conversation(conversation)
        assert (await repo.get_conversation(conversation.id)).title == "Exists"

    @pytest.mark.asyncio
    async def test_list_orders_by_most_recently_updated(self, repo):
        first = Conversation(title="First")
        await repo.save_conversation(first)
        await repo.add_message(first.id, Message(role="user", content="a"))

        second = Conversation(title="Second")
        await repo.save_conversation(second)
        await repo.add_message(second.id, Message(role="user", content="b"))

        listed = await repo.list_conversations()
        # Touching the first conversation again moves it to the front.
        await repo.add_message(first.id, Message(role="user", content="c"))
        listed = await repo.list_conversations()
        assert listed[0].id == first.id
        assert listed[1].id == second.id

    @pytest.mark.asyncio
    async def test_list_respects_limit(self, repo):
        for index in range(4):
            conversation = Conversation(title=f"Chat {index}")
            await repo.save_conversation(conversation)
            await repo.add_message(
                conversation.id, Message(role="user", content=f"m{index}")
            )

        assert len(await repo.list_conversations(limit=2)) == 2

    @pytest.mark.asyncio
    async def test_list_with_no_limit_returns_full_history(self, repo):
        """The History view needs every entry, not just the newest 10."""
        for index in range(12):
            conversation = Conversation(title=f"Chat {index}")
            await repo.save_conversation(conversation)
            await repo.add_message(
                conversation.id, Message(role="user", content=f"m{index}")
            )

        assert len(await repo.list_conversations(limit=None)) == 12

    @pytest.mark.asyncio
    async def test_delete_removes_conversation_and_messages(self, repo):
        conversation = Conversation(title="Delete me")
        await repo.save_conversation(conversation)
        await repo.add_message(conversation.id, Message(role="user", content="hi"))

        assert await repo.delete_conversation(conversation.id) is True
        with pytest.raises(KeyError):
            await repo.get_conversation(conversation.id)

        # Messages are cascade-deleted, so the conversation no longer resolves.
        with pytest.raises(KeyError):
            await repo.get_messages(conversation.id)

    @pytest.mark.asyncio
    async def test_delete_returns_false_for_unknown_conversation(self, repo):
        from uuid import uuid4

        assert await repo.delete_conversation(uuid4()) is False

    @pytest.mark.asyncio
    async def test_save_updates_existing_conversation_in_place(self, repo):
        conversation = Conversation(title="Original")
        await repo.save_conversation(conversation)

        conversation.title = "Renamed"
        await repo.save_conversation(conversation)

        listed = await repo.list_conversations()
        assert len(listed) == 1
        assert listed[0].title == "Renamed"

    @pytest.mark.asyncio
    async def test_save_survives_the_legacy_document_ids_column(self, repo):
        """The conversations table still has a document_ids column with a
        NOT NULL default. Inserts omit it, so the default must keep every write
        working — a regression here would surface as a constraint failure on
        every conversation save."""
        conversation = Conversation(title="No documents listed")
        await repo.save_conversation(conversation)

        stored = await repo.get_conversation(conversation.id)
        assert stored.title == "No documents listed"
