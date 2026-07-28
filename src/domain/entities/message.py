from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4


@dataclass
class Message:
    id: UUID = field(default_factory=uuid4)
    role: str = ""  # "user" or "assistant"
    content: str = ""
    sources: List[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def is_user(self) -> bool:
        return self.role == "user"

    @property
    def is_assistant(self) -> bool:
        return self.role == "assistant"

    def add_source(self, source: dict) -> None:
        self.sources.append(source)
