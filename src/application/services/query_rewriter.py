"""Query rewriting service: multi-query + HyDE for improved retrieval."""

import logging

from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.interfaces.llm_provider import LLMProvider
from src.domain.interfaces.query_rewriter import QueryRewriter
from src.domain.interfaces.vector_store import VectorStore

logger = logging.getLogger(__name__)


class QueryRewriterService(QueryRewriter):
    """LLM-backed query rewriter that produces multi-query variants and HyDE embeddings.

    Multi-query: asks the LLM to generate diverse search queries that
    approach the user's question from different angles.  All variants
    (including the original) are retrieved independently, and results are
    fused with Reciprocal Rank Fusion.

    HyDE (Hypothetical Document Embeddings): asks the LLM to draft a
    hypothetical answer and embeds it so the vector store returns chunks
    that would support that answer.

    TODO: ``hyde_embed`` is implemented and tested but not yet wired into
    the RAG query path — the RAG engine currently uses only ``rewrite``
    (multi-query + RRF). Wiring HyDE in is a future enhancement.
    """

    MULTI_QUERY_PROMPT = (
        "Generate {num_queries} diverse search queries that would help "
        "answer the following question. "
        "Return ONLY the queries, one per line, with no numbering or "
        "bullets.\n\n"
        "Original question: {query}\n\n"
        "Rewritten queries:"
    )

    HYDE_PROMPT = (
        "Write a detailed hypothetical answer to the following question. "
        "This will be used as a search query, so be specific and factual.\n\n"
        "Question: {query}\n\n"
        "Hypothetical answer:"
    )

    def __init__(
        self,
        llm_provider: LLMProvider,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        self._llm = llm_provider
        self._embedding = embedding_provider
        self._vector_store = vector_store

    async def rewrite(self, query: str, num_queries: int = 3) -> list[str]:
        """Generate *num_queries* query variants (original + LLM rewrites).

        Args:
            query:       The original user query.
            num_queries: Desired total number of queries.

        Returns:
            List of query strings, always starting with the original.
        """
        # Clamp to at least 1 — with num_queries=0 the original query
        # alone is returned (avoids the off-by-one `variants[:-1]`).
        num_queries = max(1, num_queries)
        prompt = self.MULTI_QUERY_PROMPT.format(num_queries=num_queries, query=query)
        response = await self._llm.generate(prompt)
        variants = [q.strip() for q in response.strip().split("\n") if q.strip()]
        # Include original + up to (num_queries - 1) variants
        queries = [query] + variants[: num_queries - 1]
        logger.debug(
            "Rewrote query into %d variants (original + %d)",
            len(queries),
            len(queries) - 1,
        )
        return queries

    async def hyde_embed(self, query: str) -> list[float]:
        """Generate a hypothetical document embedding for *query*.

        Args:
            query: The original user query.

        Returns:
            Embedding vector for the hypothetical answer.
        """
        prompt = self.HYDE_PROMPT.format(query=query)
        hypothetical = await self._llm.generate(prompt)
        logger.debug("HyDE generated %d-char hypothetical", len(hypothetical))
        return await self._embedding.embed(hypothetical)
