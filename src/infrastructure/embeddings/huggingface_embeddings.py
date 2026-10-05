import asyncio
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
        self._load_lock = asyncio.Lock()

    def _load_model(self) -> None:
        """Load the sentence-transformers model synchronously (blocking).

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

            # Update dimension from the actual model if available.
            # sentence-transformers renamed this to get_embedding_dimension();
            # fall back to the old name so either version works.
            getter = getattr(self._model, "get_embedding_dimension", None)
            if getter is None:
                getter = self._model.get_sentence_embedding_dimension
            actual_dim = getter()
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

    async def _ensure_model(self) -> None:
        """Load the model on first use without blocking the event loop.

        The first download can take seconds; run it on a worker thread and
        guard it with a lock so concurrent first-requests load it only once.
        """
        if self._model is not None:
            return
        async with self._load_lock:
            if self._model is None:
                await asyncio.to_thread(self._load_model)

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

        await self._ensure_model()

        try:
            # `encode` is a CPU-bound synchronous call; run it on a worker
            # thread so the event loop stays free for other requests.
            embedding = await asyncio.to_thread(self._model.encode, text)  # type: ignore[union-attr]
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

        await self._ensure_model()

        try:
            # Batch encoding is CPU-bound; offload to a worker thread so a
            # large ingestion batch does not stall the event loop.
            embeddings = await asyncio.to_thread(  # type: ignore[union-attr]
                self._model.encode, texts
            )
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
