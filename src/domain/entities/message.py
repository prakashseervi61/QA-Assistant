from dataclasses import dataclass, field
from datetime import datetime
from typing import List
from uuid import UUID, uuid4


@dataclass
class Message:
    id: UUID = field(default_factory=uuid4)
    role: str = ""
    content: str = ""
    sources: List[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
