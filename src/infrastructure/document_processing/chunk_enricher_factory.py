"""Factory for creating ChunkEnricher instances based on application settings."""

import logging

from src.infrastructure.config.settings import get_settings
from src.infrastructure.document_processing.chunk_enricher import ChunkEnricher

logger = logging.getLogger(__name__)


def create_chunk_enricher() -> ChunkEnricher | None:
    """Create a chunk enricher if chunk enrichment is enabled in settings.

    Returns a :class:`ChunkEnricher` when ``ENABLE_CHUNK_ENRICHMENT`` is
    ``True``, otherwise ``None``. LLM-based summaries are only enabled when
    ``ENABLE_CHUNK_ENRICHMENT_SUMMARIES`` is set AND an LLM provider can be
    created; otherwise the enricher falls back to deterministic enrichment
    (titles/sections/keywords) and a warning is logged.
    """
    settings = get_settings()
    if not settings.ENABLE_CHUNK_ENRICHMENT:
        return None

    llm_provider = None
    generate_summaries = False
    if settings.ENABLE_CHUNK_ENRICHMENT_SUMMARIES:
        try:
            from src.infrastructure.llm.factory import LLMProviderFactory

            llm_provider = LLMProviderFactory.create(settings)
            generate_summaries = True
        except Exception as exc:
            logger.warning(
                "Chunk enrichment summaries enabled but no LLM provider could "
                "be created (%s); summaries will be skipped.",
                exc,
            )

    return ChunkEnricher(
        llm_provider=llm_provider,
        generate_summaries=generate_summaries,
        max_keywords=settings.CHUNK_ENRICHMENT_MAX_KEYWORDS,
    )
