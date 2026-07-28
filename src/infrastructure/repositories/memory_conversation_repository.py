from datetime import datetime
from typing import List
from uuid import UUID

from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message
from src.domain.interfaces.conversation_repository import ConversationRepository


class MemoryConversationRepository(ConversationRepository):
    """In-memory conversation repository. Data is lost on restart."""

    def __init__(self) -> None:
        self._conversations: dict[UUID, Conversation] = {}
        self._messages: dict[UUID, List[Message]] = {}

    async def save_conversation(self, conversation: Conversation) -> None:
        existing = self._conversations.get(conversation.id)
        if existing:
            existing.title = conversation.title
            existing.document_ids = conversation.document_ids
            existing.updated_at = datetime.now()
        else:
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
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise KeyError(f"Conversation not found: {conversation_id}")
        return conversation

    async def list_conversations(self, limit: int = 10) -> List[Conversation]:
        all_conversations = list(self._conversations.values())
        all_conversations.sort(key=lambda c: c.updated_at or datetime.min, reverse=True)
        return all_conversations[:limit]

    async def add_message(self, conversation_id: UUID, message: Message) -> None:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise KeyError(f"Conversation not found: {conversation_id}")
        conversation.messages.append(message)
        conversation.updated_at = datetime.now()
        if conversation_id not in self._messages:
            self._messages[conversation_id] = []
        self._messages[conversation_id].append(message)

    async def get_messages(self, conversation_id: UUID) -> List[Message]:
        if conversation_id not in self._conversations:
            raise KeyError(f"Conversation not found: {conversation_id}")
        messages = self._messages.get(conversation_id, [])
        return sorted(messages, key=lambda m: m.created_at)

    async def delete_conversation(self, conversation_id: UUID) -> bool:
        if conversation_id not in self._conversations:
            return False
        del self._conversations[conversation_id]
        self._messages.pop(conversation_id, None)
        return True

    async def conversation_exists(self, conversation_id: UUID) -> bool:
        return conversation_id in self._conversations
