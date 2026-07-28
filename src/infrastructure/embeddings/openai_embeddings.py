import logging

from openai import AsyncOpenAI

from src.domain.interfaces.embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)

# OpenAI embedding dimension lookup by model
_OPENAI_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embedding provider using the OpenAI API.

    Uses the ``openai`` async client to generate embeddings via
    OpenAI's embedding models.

    Args:
        api_key: OpenAI API key.
        model: Embedding model identifier (e.g. ``text-embedding-3-small``).
    """

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self._api_key = api_key
        self._model = model
        self._dimension = _OPENAI_DIMENSIONS.get(model, 1536)
        self._client = AsyncOpenAI(api_key=api_key)

    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text.

        Args:
            text: The input text to embed.

        Returns:
            A list of floats representing the embedding vector.

        Raises:
            ValueError: If the input text is empty.
            RuntimeError: If the OpenAI API request fails.
        """
        if not text or not text.strip():
            raise ValueError("Input text for embedding must not be empty.")

        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as exc:
            logger.error("OpenAI embed failed for input of length %d: %s", len(text), exc)
            raise RuntimeError(f"OpenAI embedding request failed: {exc}") from exc

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of texts.

        Args:
            texts: A list of input texts to embed.

        Returns:
            A list of embedding vectors, one per input text, in the same order.

        Raises:
            ValueError: If the input list is empty.
            RuntimeError: If the OpenAI API request fails.
        """
        if not texts:
            raise ValueError("Input text list for batch embedding must not be empty.")

        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=texts,
            )
            # The API returns data in the same order as the input,
            # but we sort by index to be safe.
            sorted_data = sorted(response.data, key=lambda item: item.index)
            return [item.embedding for item in sorted_data]
        except Exception as exc:
            logger.error("OpenAI embed_batch failed for %d texts: %s", len(texts), exc)
            raise RuntimeError(f"OpenAI batch embedding request failed: {exc}") from exc

    def get_embedding_dimension(self) -> int:
        """Return the dimensionality of the embedding vectors.

        Returns:
            The embedding dimension (e.g. 1536 for ``text-embedding-3-small``).
        """
        return self._dimension
