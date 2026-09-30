"""Use cases for listing conversations, retrieving their messages, and deleting them.

Read/delete access to conversation history:
  validate → delegate to repository → map errors
"""

import logging
from uuid import UUID

from src.application.use_cases.query_document import ConversationNotFoundError
from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message
from src.domain.interfaces.conversation_repository import ConversationRepository

logger = logging.getLogger(__name__)


class ListConversationsUseCase:
    """Use case for listing recent conversations that contain messages."""

    def __init__(self, conversation_repository: ConversationRepository) -> None:
        self._repo = conversation_repository

    async def execute(self, limit: int | None = 10) -> list[Conversation]:
        """Return the most recent conversations with at least one message.

        Args:
            limit: Maximum number of conversations to return. ``None`` returns
                the full history, which is what the History view asks for.

        Returns:
            List of conversations, most recently updated first.
        """
        conversations = await self._repo.list_conversations(limit)
        filtered = [c for c in conversations if c.messages]
        logger.debug(
            "Listed %d conversations with messages (limit=%s)", len(filtered), limit
        )
        return filtered


class GetConversationUseCase:
    """Use case for retrieving all messages in a conversation."""

    def __init__(self, conversation_repository: ConversationRepository) -> None:
        self._repo = conversation_repository

    async def execute(self, conversation_id: str) -> list[Message]:
        """Return all messages in a conversation, ordered chronologically.

        Args:
            conversation_id: The conversation UUID as a string.

        Raises:
            ValueError: If conversation_id is not a valid UUID.
            ConversationNotFoundError: If the conversation does not exist.

        Returns:
            List of messages in chronological order.
        """
        try:
            conv_uuid = UUID(conversation_id)
        except ValueError:
            raise ValueError(f"Invalid conversation ID format: '{conversation_id}'")

        try:
            messages = await self._repo.get_messages(conv_uuid)
        except KeyError:
            raise ConversationNotFoundError(
                f"Conversation not found: {conversation_id}"
            )

        logger.debug("Loaded %d messages for conversation %s", len(messages), conv_uuid)
        return messages


class DeleteConversationUseCase:
    """Use case for removing a conversation and its messages from history."""

    def __init__(self, conversation_repository: ConversationRepository) -> None:
        self._repo = conversation_repository

    async def execute(self, conversation_id: str) -> bool:
        """Delete a conversation permanently.

        Args:
            conversation_id: The conversation UUID as a string.

        Returns:
            True if a conversation was deleted, False if none matched.

        Raises:
            ValueError: If conversation_id is not a valid UUID.
        """
        try:
            conv_uuid = UUID(conversation_id)
        except ValueError:
            raise ValueError(f"Invalid conversation ID format: '{conversation_id}'")

        deleted = await self._repo.delete_conversation(conv_uuid)
        logger.info(
            "Delete conversation %s (existed=%s)", conv_uuid, deleted
        )
        return deleted
