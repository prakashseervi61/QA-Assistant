from abc import ABC, abstractmethod

from src.domain.value_objects.chunk import Chunk


class VectorStore(ABC):
    """Abstract base class for vector store implementations."""

    @abstractmethod
    async def add_documents(self, chunks: list[Chunk], collection_name: str) -> None:
        """Store text chunks with their embeddings."""
        ...

    @abstractmethod
    async def similarity_search(
        self,
        query_embedding: list[float],
        k: int,
        collection_name: str,
        metadata_filter: dict[str, object] | None = None,
    ) -> list[Chunk]:
        """Retrieve the k most similar chunks to the query embedding."""
        ...

    async def hybrid_search(
        self,
        query_embedding: list[float],
        query_text: str,
        k: int = 5,
        collection_name: str = "documents",
        metadata_filter: dict[str, object] | None = None,
    ) -> list[Chunk]:
        """Hybrid search combining dense vectors and keyword matching.

        Default implementation falls back to similarity_search.
        Override in subclasses for true hybrid behavior.
        """
        return await self.similarity_search(
            query_embedding, k, collection_name, metadata_filter
        )

    @abstractmethod
    async def delete_by_metadata(self, filter_dict: dict, collection_name: str) -> None:
        """Delete chunks matching the given metadata filter."""
        ...

    @abstractmethod
    async def get_collection_count(self, collection_name: str) -> int:
        """Return the number of chunks in a collection."""
        ...

    @abstractmethod
    async def list_documents(self, collection_name: str) -> list[dict]:
        """Return a summary per ingested document in the collection."""
        ...
