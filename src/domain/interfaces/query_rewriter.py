"""Domain interface for query rewriting (multi-query + HyDE)."""

from abc import ABC, abstractmethod


class QueryRewriter(ABC):
    """Generate rewritten query variants for improved retrieval recall."""

    @abstractmethod
    async def rewrite(self, query: str, num_queries: int = 3) -> list[str]:
        """Generate rewritten query variants for improved recall.

        Args:
            query:       The original user query.
            num_queries: Desired number of query variants (including original).

        Returns:
            A list of query strings (original + rewrites).
        """
        ...

    @abstractmethod
    async def hyde_embed(self, query: str) -> list[float]:
        """Generate hypothetical document embedding (HyDE).

        Uses the LLM to draft a hypothetical answer, then embeds it so
        that the vector store retrieves chunks relevant to that answer.

        Args:
            query: The original user query.

        Returns:
            An embedding vector for the hypothetical document.
        """
        ...
