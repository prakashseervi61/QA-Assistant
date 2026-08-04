"""Abstract Reranker interface for reordering retrieved chunks."""

from abc import ABC, abstractmethod

from src.domain.value_objects.chunk import Chunk


class Reranker(ABC):
    """Abstract base class for reranker implementations.

    A reranker takes a query and a list of pre-retrieved chunks, then
    re-scores and re-orders them by relevance to the query.
    """

    @abstractmethod
    def rerank(
        self,
        query: str,
        chunks: list[Chunk],
        top_k: int = 5,
    ) -> list[Chunk]:
        """Rerank chunks by relevance to the query.

        Args:
            query:  The user's search query.
            chunks: Pre-retrieved candidate chunks.
            top_k:  Maximum number of chunks to return.

        Returns:
            The top_k most relevant chunks, sorted by descending relevance.
        """
        ...
