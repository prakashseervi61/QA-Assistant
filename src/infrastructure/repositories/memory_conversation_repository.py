from datetime import datetime
from typing import List
from uuid import UUID

from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message
from src.domain.interfaces.conversation_repository import ConversationRepository


class MemoryConversationRepository(ConversationRepository):
    """In-memory conversation repository for development and testing.

    Stores conversations and messages in Python dictionaries.
    Data is lost when the application restarts.

    This implementation is suitable for:
    - Local development
    - Unit and integration testing
    - Prototyping and demos
    """

    def __init__(self) -> None:
        self._conversations: dict[UUID, Conversation] = {}
        self._messages: dict[UUID, List[Message]] = {}

    async def save_conversation(self, conversation: Conversation) -> None:
        """Save or update a conversation.

        If the conversation already exists, updates its title, metadata,
        and sets updated_at to now. Otherwise, creates a new entry.

        Args:
            conversation: The conversation to save.
        """
        existing = self._conversations.get(conversation.id)
        if existing:
            # Update mutable fields while preserving the original timestamps
            existing.title = conversation.title
            existing.document_ids = conversation.document_ids
            existing.updated_at = datetime.now()
        else:
            # Store a copy of the conversation's current state
            self._conversations[conversation.id] = Conversation(
                id=conversation.id,
                title=conversation.title,
                messages=list(conversation.messages),
                document_ids=list(conversation.document_ids),
                created_at=conversation.created_at,
                updated_at=conversation.updated_at or datetime.now(),
            )
            self._messages[conversation.id] = list(conversation.messages)

    async def get_conversation(self, conversation_id: UUID) -> Conversation:
        """Get a conversation by ID.

        Args:
            conversation_id: The UUID of the conversation to retrieve.

        Returns:
            The conversation object.

        Raises:
            KeyError: If no conversation with the given ID exists.
        """
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise KeyError(f"Conversation not found: {conversation_id}")
        return conversation

    async def list_conversations(self, limit: int = 10) -> List[Conversation]:
        """List recent conversations, ordered by most recently updated.

        Args:
            limit: Maximum number of conversations to return. Defaults to 10.

        Returns:
            A list of conversations sorted by updated_at descending.
        """
        all_conversations = list(self._conversations.values())
        # Sort by updated_at descending (most recent first)
        all_conversations.sort(
            key=lambda c: c.updated_at or datetime.min,
            reverse=True,
        )
        return all_conversations[:limit]

    async def add_message(self, conversation_id: UUID, message: Message) -> None:
        """Add a message to a conversation.

        Appends the message to the conversation's message list and updates
        the conversation's updated_at timestamp.

        Args:
            conversation_id: The UUID of the conversation.
            message: The message to add.

        Raises:
            KeyError: If no conversation with the given ID exists.
        """
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise KeyError(f"Conversation not found: {conversation_id}")

        # Add message to conversation's message list
        conversation.messages.append(message)
        conversation.updated_at = datetime.now()

        # Also store in the messages index
        if conversation_id not in self._messages:
            self._messages[conversation_id] = []
        self._messages[conversation_id].append(message)

    async def get_messages(self, conversation_id: UUID) -> List[Message]:
        """Get all messages in a conversation, ordered by creation time.

        Args:
            conversation_id: The UUID of the conversation.

        Returns:
            A list of messages sorted by created_at ascending.

        Raises:
            KeyError: If no conversation with the given ID exists.
        """
        if conversation_id not in self._conversations:
            raise KeyError(f"Conversation not found: {conversation_id}")

        messages = self._messages.get(conversation_id, [])
        # Return a sorted copy by creation time
        return sorted(messages, key=lambda m: m.created_at)

    async def delete_conversation(self, conversation_id: UUID) -> bool:
        """Delete a conversation and all its messages.

        Args:
            conversation_id: The UUID of the conversation to delete.

        Returns:
            True if the conversation was deleted, False if not found.
        """
        if conversation_id not in self._conversations:
            return False

        del self._conversations[conversation_id]
        self._messages.pop(conversation_id, None)
        return True

    async def conversation_exists(self, conversation_id: UUID) -> bool:
        """Check if a conversation exists.

        Args:
            conversation_id: The UUID to check.

        Returns:
            True if the conversation exists, False otherwise.
        """
        return conversation_id in self._conversations
