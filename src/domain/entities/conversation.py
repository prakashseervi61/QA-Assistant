from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from src.domain.entities.message import Message


@dataclass
class Conversation:
    id: UUID = field(default_factory=uuid4)
    title: str = ""
    messages: List[Message] = field(default_factory=list)
    document_ids: List[UUID] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        self.updated_at = datetime.now()

    def add_document(self, document_id: UUID) -> None:
        if document_id not in self.document_ids:
            self.document_ids.append(document_id)
            self.updated_at = datetime.now()

    def get_last_message(self) -> Optional[Message]:
        return self.messages[-1] if self.messages else None
