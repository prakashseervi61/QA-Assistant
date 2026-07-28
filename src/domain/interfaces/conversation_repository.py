from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message


class ConversationRepository(ABC):
    """Interface for conversation persistence operations."""

    @abstractmethod
    async def save_conversation(self, conversation: Conversation) -> None:
        """Save or update a conversation."""
        pass

    @abstractmethod
    async def get_conversation(self, conversation_id: UUID) -> Conversation:
        """Get a conversation by ID.

        Raises:
            KeyError: If conversation not found.
        """
        pass

    @abstractmethod
    async def list_conversations(self, limit: int = 10) -> list[Conversation]:
        """List recent conversations, ordered by most recently updated.

        Args:
            limit: Maximum number of conversations to return.

        Returns:
            List of conversations, most recently updated first.
        """
        pass

    @abstractmethod
    async def add_message(self, conversation_id: UUID, message: Message) -> None:
        """Add a message to a conversation.

        Raises:
            KeyError: If conversation not found.
        """
        pass

    @abstractmethod
    async def get_messages(self, conversation_id: UUID) -> list[Message]:
        """Get all messages in a conversation, ordered by creation time.

        Raises:
            KeyError: If conversation not found.

        Returns:
            List of messages in chronological order.
        """
        pass

    @abstractmethod
    async def delete_conversation(self, conversation_id: UUID) -> bool:
        """Delete a conversation and all its messages.

        Returns:
            True if deleted, False if not found.
        """
        pass

    @abstractmethod
    async def conversation_exists(self, conversation_id: UUID) -> bool:
        """Check if a conversation exists."""
        pass
