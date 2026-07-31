"""Unit tests for the conversation list/get use cases."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.use_cases.conversation import (
    GetConversationUseCase,
    ListConversationsUseCase,
)
from src.application.use_cases.query_document import ConversationNotFoundError
from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message


@pytest.fixture
def mock_conversation_repo():
    """Create a mock conversation repository."""
    repo = MagicMock()
    repo.list_conversations = AsyncMock()
    repo.get_messages = AsyncMock()
    return repo


class TestListConversations:
    """ListConversationsUseCase.execute filters and delegates to the repo."""

    @pytest.mark.asyncio
    async def test_execute_filters_empty_conversations(
        self, mock_conversation_repo
    ):
        empty = Conversation(id=uuid4(), title="Empty placeholder")
        non_empty = Conversation(
            id=uuid4(),
            title="Has messages",
            messages=[Message(role="user", content="Hi")],
        )
        mock_conversation_repo.list_conversations.return_value = [
            empty,
            non_empty,
        ]

        use_case = ListConversationsUseCase(mock_conversation_repo)
        result = await use_case.execute(limit=10)

        assert result == [non_empty]

    @pytest.mark.asyncio
    async def test_execute_passes_limit_to_repo(self, mock_conversation_repo):
        mock_conversation_repo.list_conversations.return_value = []

        use_case = ListConversationsUseCase(mock_conversation_repo)
        await use_case.execute(limit=5)

        mock_conversation_repo.list_conversations.assert_awaited_once_with(5)


class TestGetConversation:
    """GetConversationUseCase.execute retrieves messages and maps errors."""

    @pytest.mark.asyncio
    async def test_execute_returns_repo_messages(self, mock_conversation_repo):
        messages = [
            Message(role="user", content="Hi"),
            Message(role="assistant", content="Hello"),
        ]
        mock_conversation_repo.get_messages.return_value = messages

        use_case = GetConversationUseCase(mock_conversation_repo)
        result = await use_case.execute(str(uuid4()))

        assert result == messages

    @pytest.mark.asyncio
    async def test_execute_maps_key_error_to_not_found(
        self, mock_conversation_repo
    ):
        mock_conversation_repo.get_messages.side_effect = KeyError("missing")

        use_case = GetConversationUseCase(mock_conversation_repo)
        with pytest.raises(ConversationNotFoundError):
            await use_case.execute(str(uuid4()))

    @pytest.mark.asyncio
    async def test_execute_rejects_invalid_uuid(self, mock_conversation_repo):
        use_case = GetConversationUseCase(mock_conversation_repo)
        with pytest.raises(ValueError):
            await use_case.execute("not-a-uuid")
