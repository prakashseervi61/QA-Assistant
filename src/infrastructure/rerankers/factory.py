"""Factory for creating reranker instances based on application settings."""

from src.domain.interfaces.reranker import Reranker
from src.infrastructure.config.settings import get_settings
from src.infrastructure.rerankers.bge_reranker import BEReranker


def create_reranker() -> Reranker | None:
    """Create a reranker if enabled in settings.

    Returns:
        A ``BEReranker`` instance if ``ENABLE_RERANKING`` is ``True``,
        otherwise ``None``.
    """
    settings = get_settings()
    if not settings.ENABLE_RERANKING:
        return None
    return BEReranker(model_name=settings.RERANKER_MODEL)
