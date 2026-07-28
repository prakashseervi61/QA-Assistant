from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

from src.domain.entities.document import Document


class DocumentRepository(ABC):
    @abstractmethod
    async def save(self, document: Document) -> Document:
        pass

    @abstractmethod
    async def find_by_id(self, document_id: UUID) -> Optional[Document]:
        pass

    @abstractmethod
    async def find_all(self) -> List[Document]:
        pass

    @abstractmethod
    async def delete(self, document_id: UUID) -> bool:
        pass

    @abstractmethod
    async def exists(self, document_id: UUID) -> bool:
        pass
