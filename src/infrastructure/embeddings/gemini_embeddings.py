import logging

import google.generativeai as genai

from src.domain.interfaces.embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)

# Gemini embedding dimension lookup by model
_GEMINI_DIMENSIONS: dict[str, int] = {
    "text-embedding-004": 768,
    "embedding-001": 768,
    "gemini-embedding-001": 3072,
}


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Embedding provider using Google Gemini API.

    Uses the ``google-generativeai`` SDK to generate embeddings via
    Google's Gemini embedding models.

    Args:
        api_key: Google AI Studio / Gemini API key.
        model: Embedding model identifier (e.g. ``text-embedding-004``).
    """

    def __init__(self, api_key: str, model: str = "text-embedding-004") -> None:
        self._api_key = api_key
        self._model = model
        self._dimension = _GEMINI_DIMENSIONS.get(model, 768)

        # Configure the SDK with the provided key
        genai.configure(api_key=api_key)

    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text.

        Args:
            text: The input text to embed.

        Returns:
            A list of floats representing the embedding vector.

        Raises:
            RuntimeError: If the Gemini API request fails.
        """
        if not text or not text.strip():
            raise ValueError("Input text for embedding must not be empty.")

        try:
            result = await genai.embed_content_async(
                model=self._model,
                content=text,
            )
            return result["embedding"]
        except Exception as exc:
            logger.error("Gemini embed failed for input of length %d: %s", len(text), exc)
            raise RuntimeError(f"Gemini embedding request failed: {exc}") from exc

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of texts.

        Args:
            texts: A list of input texts to embed.

        Returns:
            A list of embedding vectors, one per input text.

        Raises:
            ValueError: If the input list is empty.
            RuntimeError: If the Gemini API request fails.
        """
        if not texts:
            raise ValueError("Input text list for batch embedding must not be empty.")

        try:
            results = await genai.embed_content_async(
                model=self._model,
                content=texts,
            )
            return results["embedding"]
        except Exception as exc:
            logger.error("Gemini embed_batch failed for %d texts: %s", len(texts), exc)
            raise RuntimeError(f"Gemini batch embedding request failed: {exc}") from exc

    def get_embedding_dimension(self) -> int:
        """Return the dimensionality of the embedding vectors.

        Returns:
            The embedding dimension (e.g. 768 for ``text-embedding-004``).
        """
        return self._dimension
