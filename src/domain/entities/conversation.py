from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from src.domain.entities.message import Message


@dataclass
class Conversation:
    id: UUID = field(default_factory=uuid4)
    title: str = ""
    messages: list[Message] = field(default_factory=list)
    document_ids: list[UUID] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime | None = None

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        self.updated_at = datetime.now()
