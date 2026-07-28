from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class Message:
    id: UUID = field(default_factory=uuid4)
    role: str = ""
    content: str = ""
    sources: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
