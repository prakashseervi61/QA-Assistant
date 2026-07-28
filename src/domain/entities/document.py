from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4


@dataclass
class Document:
    id: UUID = field(default_factory=uuid4)
    filename: str = ""
    content: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None

    def update_content(self, new_content: str) -> None:
        self.content = new_content
        self.updated_at = datetime.now()

    def add_metadata(self, key: str, value: str) -> None:
        self.metadata[key] = value
