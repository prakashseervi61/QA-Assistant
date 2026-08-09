"""Factory for creating QueryRewriter instances based on application settings."""

from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.interfaces.llm_provider import LLMProvider
from src.domain.interfaces.query_rewriter import QueryRewriter
from src.domain.interfaces.vector_store import VectorStore
from src.infrastructure.config.settings import get_settings


def create_query_rewriter(
    llm_provider: LLMProvider,
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStore,
) -> QueryRewriter | None:
    """Create a query rewriter if enabled in settings.

    Returns:
        A ``QueryRewriterService`` instance if ``ENABLE_QUERY_REWRITING``
        is ``True``, otherwise ``None``.
    """
    settings = get_settings()
    if not settings.ENABLE_QUERY_REWRITING:
        return None

    from src.application.services.query_rewriter import QueryRewriterService

    return QueryRewriterService(llm_provider, embedding_provider, vector_store)
