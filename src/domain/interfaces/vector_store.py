from abc import ABC, abstractmethod
from src.domain.value_objects.chunk import Chunk


class VectorStore(ABC):
    """Abstract base class for vector store implementations."""

    @abstractmethod
    async def add_documents(self, chunks: list[Chunk], collection_name: str) -> None:
        """Store text chunks with their embeddings."""
        ...

    @abstractmethod
    async def similarity_search(self, query_embedding: list[float], k: int, collection_name: str) -> list[Chunk]:
        """Retrieve the k most similar chunks to the query embedding."""
        ...

    @abstractmethod
    async def delete_by_metadata(self, filter_dict: dict, collection_name: str) -> None:
        """Delete chunks matching the given metadata filter."""
        ...

    @abstractmethod
    async def get_collection_count(self, collection_name: str) -> int:
        """Return the number of chunks in a collection."""
        ...
