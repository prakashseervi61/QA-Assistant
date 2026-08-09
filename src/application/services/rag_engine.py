"""RAG (Retrieval-Augmented Generation) query engine.

Orchestrates the full RAG pipeline:
  embed question → retrieve context → build prompt → generate answer
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.interfaces.llm_provider import LLMProvider, LLMQuotaExceededError
from src.domain.interfaces.query_rewriter import QueryRewriter
from src.domain.interfaces.reranker import Reranker
from src.domain.interfaces.vector_store import VectorStore
from src.infrastructure.config.settings import get_settings

if TYPE_CHECKING:
    from src.domain.value_objects.chunk import Chunk

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
        reranker: Reranker | None = None,
        query_rewriter: QueryRewriter | None = None,
    ) -> None:
        self._llm = llm_provider
        self._embedding = embedding_provider
        self._vector_store = vector_store
        self._reranker = reranker
        self._query_rewriter = query_rewriter
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def query(
        self,
        question: str,
        top_k: int | None = None,
        metadata_filter: dict[str, object] | None = None,
    ) -> dict:
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

            # 2. Retrieve similar chunks
            base_collection = self._settings.CHROMA_COLLECTION_NAME
            use_parent_child = getattr(self._settings, "ENABLE_PARENT_CHILD", False)
            # With parent-child retrieval enabled, search the child chunks
            # and expand the winners to their parents afterwards.
            collection = (
                f"{base_collection}_child" if use_parent_child else base_collection
            )
            use_rewrite = (
                getattr(self._settings, "ENABLE_QUERY_REWRITING", False)
                and self._query_rewriter is not None
            )
            rewriter = self._query_rewriter

            chunks: list | None = None
            if use_rewrite and rewriter is not None:
                try:
                    num_variants = getattr(
                        self._settings, "QUERY_REWRITING_VARIANTS", 3
                    )
                    queries = await rewriter.rewrite(
                        question, num_queries=num_variants
                    )
                    logger.debug(
                        "Multi-query retrieval: %d variants", len(queries)
                    )

                    all_result_lists: list[list] = []
                    for q in queries:
                        q_emb = await self._embedding.embed(q)
                        if getattr(
                            self._settings, "ENABLE_HYBRID_SEARCH", False
                        ):
                            q_chunks = await self._vector_store.hybrid_search(
                                query_embedding=q_emb,
                                query_text=q,
                                k=k,
                                collection_name=collection,
                                metadata_filter=metadata_filter,
                            )
                        else:
                            q_chunks = (
                                await self._vector_store.similarity_search(
                                    query_embedding=q_emb,
                                    k=k,
                                    collection_name=collection,
                                    metadata_filter=metadata_filter,
                                )
                            )
                        all_result_lists.append(q_chunks)

                    chunks = self._rrf_fuse(all_result_lists, k)
                    logger.info(
                        "RRF fused %d query lists → %d chunks",
                        len(all_result_lists),
                        len(chunks),
                    )
                except LLMQuotaExceededError:
                    # 429 must propagate so the API can respond with 429.
                    raise
                except Exception as exc:
                    logger.warning(
                        "Query rewriting failed (%s); falling back to "
                        "single-query retrieval",
                        exc,
                    )
                    chunks = None

            if chunks is None:
                query_embedding = await self._embedding.embed(question)
                if getattr(
                    self._settings, "ENABLE_HYBRID_SEARCH", False
                ):
                    chunks = await self._vector_store.hybrid_search(
                        query_embedding=query_embedding,
                        query_text=question,
                        k=k,
                        collection_name=collection,
                        metadata_filter=metadata_filter,
                    )
                else:
                    chunks = await self._vector_store.similarity_search(
                        query_embedding=query_embedding,
                        k=k,
                        collection_name=collection,
                        metadata_filter=metadata_filter,
                    )
            logger.info("Retrieved %d context chunks", len(chunks))

            # Parent-child retrieval: swap the retrieved children for their
            # parent chunks, which carry the fuller context for the prompt.
            if use_parent_child and chunks:
                chunks = await self._expand_children_to_parents(
                    chunks, f"{base_collection}_parent"
                )

            # rerank
            if self._reranker is not None and chunks:
                chunks = await asyncio.to_thread(
                    self._reranker.rerank, question, chunks, k
                )

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
        self,
        question: str,
        top_k: int | None = None,
        metadata_filter: dict[str, object] | None = None,
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
            base_collection = self._settings.CHROMA_COLLECTION_NAME
            use_parent_child = getattr(self._settings, "ENABLE_PARENT_CHILD", False)
            # With parent-child retrieval enabled, search the child chunks
            # and expand the winners to their parents afterwards.
            collection = (
                f"{base_collection}_child" if use_parent_child else base_collection
            )
            rewriter = self._query_rewriter
            use_rewrite = (
                getattr(self._settings, "ENABLE_QUERY_REWRITING", False)
                and rewriter is not None
            )

            chunks: list | None = None
            if use_rewrite and rewriter is not None:
                try:
                    num_variants = getattr(
                        self._settings, "QUERY_REWRITING_VARIANTS", 3
                    )
                    queries = await rewriter.rewrite(
                        question, num_queries=num_variants
                    )

                    all_result_lists: list[list] = []
                    for q in queries:
                        q_emb = await self._embedding.embed(q)
                        if getattr(
                            self._settings, "ENABLE_HYBRID_SEARCH", False
                        ):
                            q_chunks = await self._vector_store.hybrid_search(
                                query_embedding=q_emb,
                                query_text=q,
                                k=k,
                                collection_name=collection,
                                metadata_filter=metadata_filter,
                            )
                        else:
                            q_chunks = (
                                await self._vector_store.similarity_search(
                                    query_embedding=q_emb,
                                    k=k,
                                    collection_name=collection,
                                    metadata_filter=metadata_filter,
                                )
                            )
                        all_result_lists.append(q_chunks)

                    chunks = self._rrf_fuse(all_result_lists, k)
                except LLMQuotaExceededError:
                    # 429 must propagate so the API can respond with 429.
                    raise
                except Exception as exc:
                    logger.warning(
                        "Query rewriting failed (%s); falling back to "
                        "single-query retrieval",
                        exc,
                    )
                    chunks = None

            if chunks is None:
                query_embedding = await self._embedding.embed(question)
                if getattr(
                    self._settings, "ENABLE_HYBRID_SEARCH", False
                ):
                    chunks = await self._vector_store.hybrid_search(
                        query_embedding=query_embedding,
                        query_text=question,
                        k=k,
                        collection_name=collection,
                        metadata_filter=metadata_filter,
                    )
                else:
                    chunks = await self._vector_store.similarity_search(
                        query_embedding=query_embedding,
                        k=k,
                        collection_name=collection,
                        metadata_filter=metadata_filter,
                    )
            logger.debug("Retrieved %d chunks for streaming query", len(chunks))

            # Parent-child retrieval: swap the retrieved children for their
            # parent chunks, which carry the fuller context for the prompt.
            if use_parent_child and chunks:
                chunks = await self._expand_children_to_parents(
                    chunks, f"{base_collection}_parent"
                )

            # rerank
            if self._reranker is not None and chunks:
                chunks = await asyncio.to_thread(
                    self._reranker.rerank, question, chunks, k
                )

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
    # Parent-child retrieval
    # ------------------------------------------------------------------

    @staticmethod
    async def _expand_to_parents(
        vector_store: VectorStore,
        parent_ids: list[str],
        parent_collection: str,
    ) -> list["Chunk"]:
        """Look up parent chunks by their IDs.

        Args:
            vector_store:      The vector store to query.
            parent_ids:        List of parent chunk ID strings.
            parent_collection: Name of the parent chunk collection.

        Returns:
            List of parent chunks found. Missing IDs are silently skipped.
        """
        # Deduplicate internally — duplicate ids would only waste lookups
        # and could duplicate the returned chunks.
        parent_ids = list(dict.fromkeys(parent_ids))

        if not parent_ids:
            return []

        # Use get_documents_by_ids if available, else fall back to search
        if hasattr(vector_store, "get_documents_by_ids"):
            return await vector_store.get_documents_by_ids(
                parent_ids, parent_collection
            )

        # Fallback: search with filter
        all_parents: list[Chunk] = []
        for pid in parent_ids:
            chunks = await vector_store.similarity_search(
                query_embedding=[0.0],  # dummy — we just want to filter
                k=1,
                collection_name=parent_collection,
                metadata_filter={"id": pid},
            )
            all_parents.extend(chunks)
        return all_parents

    async def _expand_children_to_parents(
        self,
        chunks: list["Chunk"],
        parent_collection: str,
    ) -> list["Chunk"]:
        """Expand retrieved child chunks to their parent chunks.

        Collects the unique ``parent_id`` values from the retrieved
        children, fetches the parent chunks, and returns them deduplicated
        by chunk id with order preserved. If no children carry a
        ``parent_id``, or no parents are found, the original chunks are
        returned unchanged (graceful fallback for documents ingested
        before parent-child retrieval was enabled).
        """
        parent_ids: list[str] = []
        for chunk in chunks:
            pid = chunk.metadata.get("parent_id")
            if pid and pid not in parent_ids:
                parent_ids.append(pid)

        if not parent_ids:
            return chunks

        parents = await self._expand_to_parents(
            self._vector_store, parent_ids, parent_collection
        )
        if not parents:
            return chunks

        seen: set[str] = set()
        unique_parents: list[Chunk] = []
        for parent in parents:
            key = str(parent.id)
            if key not in seen:
                seen.add(key)
                unique_parents.append(parent)
        return unique_parents

    # ------------------------------------------------------------------
    # RRF Fusion
    # ------------------------------------------------------------------

    @staticmethod
    def _rrf_fuse(
        all_chunks: list[list["Chunk"]], k: int, rrf_k: int = 60
    ) -> list["Chunk"]:
        """Reciprocal Rank Fusion across multiple query result lists.

        Args:
            all_chunks: List of ranked chunk lists (one per query).
            k:          Maximum chunks to return.
            rrf_k:      RRF constant (default 60, standard in literature).

        Returns:
            Top-k chunks sorted by fused RRF score.
        """
        from collections import defaultdict

        chunk_scores: dict[str, float] = defaultdict(float)
        chunk_map: dict[str, Chunk] = {}

        for rank_list in all_chunks:
            for rank, chunk in enumerate(rank_list):
                chunk_id = str(chunk.id)
                chunk_scores[chunk_id] += 1.0 / (rrf_k + rank + 1)
                # Keep the occurrence with the highest similarity score so
                # the winning chunk is the best representative of its id.
                try:
                    current_score = float(chunk.metadata.get("score", 0.0))
                except (TypeError, ValueError):
                    current_score = 0.0
                previous = chunk_map.get(chunk_id)
                if previous is None:
                    chunk_map[chunk_id] = chunk
                else:
                    try:
                        previous_score = float(
                            previous.metadata.get("score", 0.0)
                        )
                    except (TypeError, ValueError):
                        previous_score = 0.0
                    if current_score > previous_score:
                        chunk_map[chunk_id] = chunk

        sorted_ids = sorted(
            chunk_scores.keys(),
            key=lambda cid: chunk_scores[cid],
            reverse=True,
        )
        return [chunk_map[cid] for cid in sorted_ids[:k]]

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
