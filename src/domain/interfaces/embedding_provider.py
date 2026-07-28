from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Abstract base class for all embedding provider implementations."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of texts."""
        ...

    @abstractmethod
    def get_embedding_dimension(self) -> int:
        """Return the dimensionality of the embedding vectors."""
        ...
