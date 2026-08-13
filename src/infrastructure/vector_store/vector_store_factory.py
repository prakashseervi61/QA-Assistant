"""Vector store factory: Qdrant when configured, ChromaDB otherwise."""

import logging

from src.domain.interfaces.vector_store import VectorStore
from src.infrastructure.config.settings import get_settings
from src.infrastructure.vector_store.chroma_store import ChromaStore
from src.infrastructure.vector_store.qdrant_store import QdrantVectorStore

logger = logging.getLogger(__name__)


def create_vector_store() -> VectorStore:
    """Create the configured vector store backend.

    Returns a Qdrant-backed store when ``VECTOR_STORE_BACKEND`` is
    ``"qdrant"`` and the optional ``qdrant-client`` dependency is
    available; otherwise falls back to the local ChromaDB store (the
    default, preserving previous behaviour). Never raises: an unknown
    backend value or a Qdrant construction failure logs a warning and
    falls back to ChromaDB so the application always boots.
    """
    settings = get_settings()
    backend = getattr(settings, "VECTOR_STORE_BACKEND", "chroma")
    store: VectorStore

    if backend == "qdrant":
        try:
            store = QdrantVectorStore(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY,
            )
        except Exception as exc:
            logger.warning(
                "Qdrant vector store unavailable (%s); falling back to ChromaDB",
                exc,
            )
            store = ChromaStore(persist_directory=settings.CHROMA_PERSIST_DIR)
    elif backend == "chroma":
        store = ChromaStore(persist_directory=settings.CHROMA_PERSIST_DIR)
    else:
        logger.warning(
            "Unknown VECTOR_STORE_BACKEND=%r; falling back to ChromaDB",
            backend,
        )
        store = ChromaStore(persist_directory=settings.CHROMA_PERSIST_DIR)

    logger.info("Using %s vector store", type(store).__name__)
    return store
