from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.infrastructure.config.settings import Settings


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Build the local HuggingFace embedding provider.

    ponytail: this was a switch over three providers; only the local
    sentence-transformers one is used, so the switch is gone. The import stays
    lazy so the (heavy) model library is not pulled in at module import time.
    """
    from src.infrastructure.embeddings.huggingface_embeddings import (
        HuggingFaceEmbeddingProvider,
    )

    return HuggingFaceEmbeddingProvider(model_name=settings.HUGGINGFACE_MODEL)