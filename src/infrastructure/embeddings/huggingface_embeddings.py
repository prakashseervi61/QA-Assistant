import logging
from typing import TYPE_CHECKING

from src.domain.interfaces.embedding_provider import EmbeddingProvider

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# HuggingFace embedding dimension lookup by model
_HF_DIMENSIONS: dict[str, int] = {
    "all-MiniLM-L6-v2": 384,
    "all-MiniLM-L12-v2": 384,
    "all-mpnet-base-v2": 768,
}


class HuggingFaceEmbeddingProvider(EmbeddingProvider):
    """Embedding provider using local HuggingFace sentence-transformers models.

    Models are lazily loaded on the first embedding call to avoid
    blocking application startup with large model downloads.

    Args:
        model_name: HuggingFace model identifier
            (e.g. ``all-MiniLM-L6-v2``).
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model: SentenceTransformer | None = None
        self._dimension: int = _HF_DIMENSIONS.get(model_name, 384)

    def _load_model(self) -> None:
        """Lazy-load the sentence-transformers model.

        The model is downloaded from HuggingFace Hub on first use and
        cached locally for subsequent calls.

        Raises:
            RuntimeError: If the model fails to load.
        """
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading HuggingFace model: %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)

            # Update dimension from the actual model if available
            actual_dim = self._model.get_sentence_embedding_dimension()
            if actual_dim:
                self._dimension = actual_dim

            logger.info(
                "HuggingFace model loaded: %s (dim=%d)",
                self._model_name,
                self._dimension,
            )
        except Exception as exc:
            logger.error(
                "Failed to load HuggingFace model '%s': %s", self._model_name, exc
            )
            raise RuntimeError(
                f"Failed to load HuggingFace model '{self._model_name}': {exc}"
            ) from exc

    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text.

        Args:
            text: The input text to embed.

        Returns:
            A list of floats representing the embedding vector.

        Raises:
            ValueError: If the input text is empty.
            RuntimeError: If the model fails to load or encode the text.
        """
        if not text or not text.strip():
            raise ValueError("Input text for embedding must not be empty.")

        self._load_model()

        try:
            embedding = self._model.encode(text)  # type: ignore[union-attr]
            return embedding.tolist()
        except Exception as exc:
            logger.error(
                "HuggingFace embed failed for input of length %d: %s", len(text), exc
            )
            raise RuntimeError(f"HuggingFace embedding failed: {exc}") from exc

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of texts.

        Uses the model's batch encoding for efficient processing.

        Args:
            texts: A list of input texts to embed.

        Returns:
            A list of embedding vectors, one per input text.

        Raises:
            ValueError: If the input list is empty.
            RuntimeError: If the model fails to load or encode the texts.
        """
        if not texts:
            raise ValueError("Input text list for batch embedding must not be empty.")

        self._load_model()

        try:
            embeddings = self._model.encode(texts)  # type: ignore[union-attr]
            return [emb.tolist() for emb in embeddings]
        except Exception as exc:
            logger.error(
                "HuggingFace embed_batch failed for %d texts: %s", len(texts), exc
            )
            raise RuntimeError(f"HuggingFace batch embedding failed: {exc}") from exc

    def get_embedding_dimension(self) -> int:
        """Return the dimensionality of the embedding vectors.

        Returns:
            The embedding dimension (e.g. 384 for ``all-MiniLM-L6-v2``).
        """
        return self._dimension
