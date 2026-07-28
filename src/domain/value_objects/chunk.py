from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID, uuid4


@dataclass(frozen=True)
class Chunk:
    id: UUID = field(default_factory=uuid4)
    document_id: UUID = field(default_factory=uuid4)
    content: str = ""
    embedding: Optional[List[float]] = None
    metadata: dict = field(default_factory=dict)
    chunk_index: int = 0

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "content": self.content,
            "metadata": self.metadata,
            "chunk_index": self.chunk_index,
        }
