"""RAG (Retrieval-Augmented Generation) query engine.

Orchestrates the full RAG pipeline:
  embed question → retrieve context → build prompt → generate answer
"""

import logging
from collections.abc import AsyncIterator

from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.interfaces.llm_provider import LLMProvider, LLMQuotaExceededError
from src.domain.interfaces.vector_store import VectorStore
from src.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)


class RAGQueryError(Exception):
    """Raised when a RAG query fails."""


class RAGEngine:
    """RAG query engine that retrieves context and generates answers.

    Pipeline:
        1. Embed the user question
        2. Search vector store for similar chunks
        3. Build a prompt with retrieved context
        4. Generate answer using LLM
        5. Return answer with source citations

    Args:
        llm_provider:      LLM provider for text generation.
        embedding_provider: Embedding provider for query embedding.
        vector_store:      Vector store for similarity search.
    """

    DEFAULT_TOP_K = 5
    MAX_CONTEXT_CHUNKS = 10

    NO_DOCUMENTS_MESSAGE = (
        "No documents have been uploaded yet. Please upload a PDF, DOCX, or TXT "
        "document from the Documents view, then ask your question again."
    )

    NO_RELEVANT_CONTEXT_MESSAGE = (
        "I couldn't find a relevant answer in the uploaded documents. "
        "Try rephrasing your question or uploading more documents."
    )

    PROMPT_TEMPLATE = (
        "You are a helpful assistant that answers questions "
        "based on the provided context.\n\n"
        "Context from documents:\n{context}\n\n"
        "Question: {question}\n\n"
        "Instructions:\n"
        "- Answer the question based on the context provided\n"
        "- If the context doesn't contain enough information, "
        "say so clearly\n"
        "- Cite your sources when possible by referencing the "
        "document names\n"
        "- Be concise and accurate\n"
        "- If multiple sources provide different information, "
        "mention both perspectives"
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
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def query(self, question: str, top_k: int | None = None) -> dict:
        """Process a query: embed → retrieve → generate.

        Args:
            question: The user's natural-language question.
            top_k:    Number of context chunks to retrieve.
                      Defaults to ``DEFAULT_TOP_K``.

        Returns:
            A dict with keys:
                - answer    (str)   – generated answer
                - sources   (list)  – source chunks with metadata
                - confidence (float) – average similarity score

        Raises:
            RAGQueryError: On any failure during the pipeline.
        """
        k = top_k or self.DEFAULT_TOP_K

        try:
            # 1. Embed the question
            logger.debug("Embedding question (len=%d)", len(question))
            query_embedding = await self._embedding.embed(question)

            # 2. Retrieve similar chunks
            logger.debug("Searching vector store (top_k=%d)", k)
            collection = self._settings.CHROMA_COLLECTION_NAME
            chunks = await self._vector_store.similarity_search(
                query_embedding=query_embedding,
                k=k,
                collection_name=collection,
            )
            logger.info("Retrieved %d context chunks", len(chunks))

            if not chunks:
                return await self._empty_retrieval_response(collection)

            # 3. Build prompt with context
            prompt = self._build_prompt(question, chunks)

            # 4. Generate answer
            logger.debug("Generating answer via %s", self._llm.get_model_name())
            answer = await self._llm.generate(prompt)
            logger.info("Generated answer (len=%d)", len(answer))

            # 5. Format sources and compute confidence
            sources = self._format_sources(chunks)
            confidence = self._compute_confidence(chunks)

            return {
                "answer": answer,
                "sources": sources,
                "confidence": confidence,
            }

        except RAGQueryError:
            raise
        except LLMQuotaExceededError:
            raise
        except Exception as exc:
            logger.error("RAG query failed: %s", exc, exc_info=True)
            raise RAGQueryError(f"Failed to process query: {exc}") from exc

    async def query_stream(
        self, question: str, top_k: int | None = None
    ) -> AsyncIterator[str]:
        """Process a query with streaming response.

        Args:
            question: The user's natural-language question.
            top_k:    Number of context chunks to retrieve.

        Yields:
            Chunks of the generated answer as they arrive.

        Raises:
            RAGQueryError: On any failure during the pipeline.
        """
        k = top_k or self.DEFAULT_TOP_K

        try:
            # 1. Embed the question
            query_embedding = await self._embedding.embed(question)

            # 2. Retrieve similar chunks
            collection = self._settings.CHROMA_COLLECTION_NAME
            chunks = await self._vector_store.similarity_search(
                query_embedding=query_embedding,
                k=k,
                collection_name=collection,
            )
            logger.debug("Retrieved %d chunks for streaming query", len(chunks))

            if not chunks:
                count = await self._vector_store.get_collection_count(collection)
                message = (
                    self.NO_DOCUMENTS_MESSAGE
                    if count == 0
                    else self.NO_RELEVANT_CONTEXT_MESSAGE
                )
                logger.info(
                    "No context retrieved for streaming query "
                    "(chunks_in_collection=%d)",
                    count,
                )
                yield message
                return

            # 3. Build prompt with context
            prompt = self._build_prompt(question, chunks)

            # 4. Stream answer
            async for chunk in self._llm.generate_stream(prompt):
                yield chunk

        except RAGQueryError:
            raise
        except LLMQuotaExceededError:
            raise
        except Exception as exc:
            logger.error("RAG stream query failed: %s", exc, exc_info=True)
            raise RAGQueryError(f"Failed to stream query: {exc}") from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _empty_retrieval_response(self, collection: str) -> dict:
        """Return a friendly response when no context chunks were retrieved.

        Distinguishes between "no documents uploaded yet" (empty
        collection) and "documents exist but nothing relevant matched".

        Args:
            collection: Name of the vector store collection checked.

        Returns:
            A dict with ``answer``, ``sources``, and ``confidence`` keys.
        """
        count = await self._vector_store.get_collection_count(collection)
        if count == 0:
            logger.info("No documents in collection '%s'", collection)
            return {
                "answer": self.NO_DOCUMENTS_MESSAGE,
                "sources": [],
                "confidence": 0.0,
            }
        logger.info("No relevant chunks retrieved from collection '%s'", collection)
        return {
            "answer": self.NO_RELEVANT_CONTEXT_MESSAGE,
            "sources": [],
            "confidence": 0.0,
        }

    def _build_prompt(self, question: str, chunks: list) -> str:
        """Build the RAG prompt with retrieved context and question.

        Args:
            question: The user's question.
            chunks:   Retrieved text chunks for context.

        Returns:
            The formatted prompt string.
        """
        context_parts = []
        for i, chunk in enumerate(chunks[: self.MAX_CONTEXT_CHUNKS], 1):
            filename = chunk.metadata.get("filename", "Unknown")
            page = chunk.metadata.get("page", "")
            page_info = f" (page {page})" if page else ""
            context_parts.append(
                f"[Source {i}: {filename}{page_info}]\n{chunk.content}"
            )

        context = "\n\n".join(context_parts)

        if not context:
            context = "No relevant context found in the documents."

        return self.PROMPT_TEMPLATE.format(
            context=context,
            question=question,
        )

    def _format_sources(self, chunks: list) -> list[dict]:
        """Format retrieved chunks as source citations.

        Args:
            chunks: Retrieved text chunks.

        Returns:
            A list of source dicts with content, metadata, score, and chunk_index.
        """
        sources = []
        for chunk in chunks:
            # Extract score from metadata (stored by ChromaStore during search)
            score = chunk.metadata.get("score", 0.0)
            # Create a copy of metadata without the score to avoid duplication
            display_metadata = {k: v for k, v in chunk.metadata.items() if k != "score"}
            sources.append(
                {
                    "content": chunk.content[:500],
                    "metadata": display_metadata,
                    "score": round(float(score), 4),
                    "chunk_index": chunk.chunk_index,
                }
            )
        return sources

    def _compute_confidence(self, chunks: list) -> float:
        """Compute confidence score from chunk similarity scores.

        Args:
            chunks: Retrieved text chunks.

        Returns:
            Average similarity score (0.0 to 1.0).
        """
        if not chunks:
            return 0.0

        scores = []
        for chunk in chunks:
            score = chunk.metadata.get("score", 0.0)
            if isinstance(score, (int, float)):
                scores.append(float(score))

        return sum(scores) / len(scores) if scores else 0.0
