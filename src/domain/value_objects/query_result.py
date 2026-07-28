from dataclasses import dataclass, field
from typing import List
from uuid import UUID


@dataclass(frozen=True)
class QueryResult:
    chunk_id: UUID = field(default_factory=UUID)
    document_id: UUID = field(default_factory=UUID)
    content: str = ""
    score: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def is_relevant(self) -> bool:
        return self.score > 0.5
