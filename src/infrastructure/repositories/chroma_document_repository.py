from typing import List, Optional
from uuid import UUID

from src.domain.entities.document import Document
from src.domain.interfaces.document_repository import DocumentRepository
from src.infrastructure.config.settings import get_settings
from src.infrastructure.vector_store.chroma_store import ChromaStore


class ChromaDocumentRepository(DocumentRepository):
    def __init__(self, vector_store: ChromaStore):
        self.vector_store = vector_store

    def _collection_name(self) -> str:
        return get_settings().CHROMA_COLLECTION_NAME

    async def save(self, document: Document) -> Document:
        return document

    async def find_by_id(self, document_id: UUID) -> Optional[Document]:
        results = await self.vector_store.similarity_search(
            query_embedding=[0.0] * 384,
            k=1,
            collection_name=self._collection_name(),
        )
        if results:
            return Document(
                id=document_id,
                content=results[0].content,
                metadata=results[0].metadata,
            )
        return None

    async def find_all(self) -> List[Document]:
        count = await self.vector_store.get_collection_count(
            self._collection_name()
        )
        return []

    async def delete(self, document_id: UUID) -> bool:
        await self.vector_store.delete_by_metadata(
            filter_dict={"document_id": str(document_id)},
            collection_name=self._collection_name(),
        )
        return True

    async def exists(self, document_id: UUID) -> bool:
        doc = await self.find_by_id(document_id)
        return doc is not None
