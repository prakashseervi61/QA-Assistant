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
from src.domain.interfaces.reranker import Reranker
from src.domain.interfaces.vector_store import VectorStore
from src.infrastructure.config.settings import get_settings
from src.infrastructure.llm.prompt_registry import (
    PROMPT_VERSIONS,
    get_prompt,
)
from src.infrastructure.llm.structured_output import (
    StructuredOutputError,
    generate_structured_answer,
)

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
        reranker:          Optional reranker applied after retrieval.
        tracer:            Optional OpenTelemetry-style tracer.
        guardrail_manager: Optional guardrail manager. When provided, the
                           user question is checked (PII + prompt injection)
                           before retrieval and the generated answer is
                           checked (groundedness + PII leak) afterwards;
                           results are merged into the response metadata
                           under ``"guardrails"`` (streaming mode attaches
                           them to the final ``done`` event). When None
                           (default), the pipeline behaves exactly as before.
    """

    DEFAULT_TOP_K = 5
    MAX_CONTEXT_CHUNKS = 10

    BLOCKED_MESSAGE = "Your request was blocked by safety filters."

    NO_DOCUMENTS_MESSAGE = (
        "No documents have been uploaded yet. Please upload a PDF, DOCX, or TXT "
        "document from the Documents view, then ask your question again."
    )

    NO_RELEVANT_CONTEXT_MESSAGE = (
        "I couldn't find a relevant answer in the uploaded documents. "
        "Try rephrasing your question or uploading more documents."
    )

    def __init__(
        self,
        llm_provider: LLMProvider,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        reranker: Reranker | None = None,
        guardrail_manager: object | None = None,
    ) -> None:
        self._llm = llm_provider
        self._embedding = embedding_provider
        self._vector_store = vector_store
        self._reranker = reranker
        self._guardrail_manager = guardrail_manager
        self._settings = get_settings()

    @staticmethod
    def _stage_event(stage: str, detail: str) -> dict[str, str]:
        """Build a streaming ``stage`` event announcing a pipeline step.

        Stage events are additive to the streaming contract: clients that
        only expect raw text chunks keep working, while clients that render
        a retrieval trace can show which pipeline step is running.

        Args:
            stage:  Stable identifier, e.g. ``"retrieving"``.
            detail: Short human-readable description of the step.

        Returns:
            A dict with ``type``, ``stage`` and ``detail`` keys.
        """
        return {"type": "stage", "stage": stage, "detail": detail}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def query(
        self,
        question: str,
        top_k: int | None = None,
        metadata_filter: dict[str, object] | None = None,
        use_structured_output: bool = False,
    ) -> dict:
        """Process a query: embed → retrieve → generate.

        Args:
            question: The user's natural-language question.
            top_k:    Number of context chunks to retrieve.
                      Defaults to ``DEFAULT_TOP_K``.
            use_structured_output: When True, the LLM is asked for a JSON
                      answer with citations (``StructuredAnswer`` shape)
                      instead of free-form text. On any parse failure the
                      engine falls back to the default generation path.

        Note:
            When query rewriting is enabled, the LLM is invoked twice per
            query — once to rewrite the question and once to generate the
            answer.

        Returns:
            A dict with keys:
                - answer    (str)  – generated answer
                - sources   (list) – source chunks with metadata
                - confidence (float) – average similarity score

            With ``use_structured_output=True`` the dict instead carries:
                - answer    (str)  – structured answer text
                - citations (list) – [chunk_id, source, page, excerpt] dicts
                - confidence (float)
                - metadata  (dict) – {"mode": "structured"}

        Raises:
            RAGQueryError: On any failure during the pipeline.
        """
        k = top_k or self.DEFAULT_TOP_K

        try:
            # 0. Prompt version selection (settings + optional A/B knob).
            # Purely deterministic from the question, so it can be
            # computed once and attached to every finalized response.
            selected_version = self._select_prompt_version()

            # 0. Guardrails: input check (pre-retrieval, optional). Never
            # crashes the pipeline — on any failure we log and pass through.
            guardrail_metadata: dict[str, object] | None = None
            if self._guardrail_manager is not None:
                input_check = self._check_input(question)
                guardrail_metadata = {"input": input_check, "output": {}}
                if input_check.get("blocked", False):
                    logger.info("Query blocked by input guardrails")
                    return self._finalize(
                        {
                            "answer": self.BLOCKED_MESSAGE,
                            "sources": [],
                            "confidence": 0.0,
                        },
                        guardrail_metadata,
                        prompt_version=selected_version,
                    )

            # 1. Embed the question
            logger.debug("Embedding question (len=%d)", len(question))

            # 2. Retrieve similar chunks
            base_collection = self._settings.CHROMA_COLLECTION_NAME
            collection = base_collection

            query_embedding = await self._embedding.embed(question)
            if getattr(self._settings, "ENABLE_HYBRID_SEARCH", False):
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


            # rerank
            if self._reranker is not None and chunks:
                chunks = await asyncio.to_thread(
                    self._reranker.rerank, question, chunks, k
                )

            if not chunks:
                result = await self._empty_retrieval_response(collection)
                return self._finalize(
                    result, guardrail_metadata, prompt_version=selected_version
                )

            # Structured output path (optional, feature-flagged): ask the LLM
            # for a JSON answer with citations instead of free-form text.
            if use_structured_output:
                try:
                    structured = await generate_structured_answer(
                        llm_provider=self._llm,
                        question=question,
                        chunks=chunks,
                    )
                    result = {
                        "answer": structured.answer,
                        "citations": [
                            {
                                "chunk_id": c.chunk_id,
                                "source": c.source,
                                "page": c.page,
                                "excerpt": c.excerpt,
                            }
                            for c in structured.citations
                        ],
                        "confidence": structured.confidence,
                        "metadata": {"mode": "structured"},
                    }
                    return self._finalize(
                        result,
                        guardrail_metadata,
                        structured.answer,
                        chunks,
                        selected_version,
                    )
                except StructuredOutputError as exc:
                    logger.warning(
                        "Structured output failed (%s); falling back to default",
                        exc,
                    )
                    # fall through to the normal generation path

            # 3. Build prompt with context
            prompt = self._build_prompt(question, chunks, selected_version)

            # 4. Generate answer
            logger.debug("Generating answer via %s", self._llm.get_model_name())
            answer = await self._llm.generate(prompt)
            logger.info("Generated answer (len=%d)", len(answer))

            # 5. Format sources and compute confidence
            sources = self._format_sources(chunks)
            confidence = self._compute_confidence(chunks)

            result = {
                "answer": answer,
                "sources": sources,
                "confidence": confidence,
            }
            return self._finalize(
                result, guardrail_metadata, answer, chunks, selected_version
            )

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
    ) -> AsyncIterator[str | dict[str, object]]:
        """Process a query with streaming response.

        Note:
            Structured output is intentionally NOT supported here: JSON-mode
            generation does not stream reliably, so ``query_stream`` always
            uses the default free-form generation path. Callers that need
            citations should use :meth:`query` with
            ``use_structured_output=True``.

        Note:
            The stream always ends with a ``{"type": "done", ...}`` event
            carrying the ``answer``, the ``sources`` that backed it, and the
            ``confidence`` score, so callers never need a second retrieval
            pass just to collect citations.

            When a guardrail manager is wired in, the user question is
            checked (PII + prompt injection) before retrieval and the
            generated answer is checked (groundedness + PII leak) after
            generation. A blocked question ends the stream with a
            ``{"type": "blocked", ...}`` event before any LLM call; a
            successful stream ends with a ``{"type": "done", ...}`` event
            that also carries the guardrail results.

        Args:
            question: The user's natural-language question.
            top_k:    Number of context chunks to retrieve.

        Yields:
            Raw answer text chunks as they arrive, interleaved with
            ``{"type": "stage", "stage": <name>, "detail": <text>}`` events
            that announce each retrieval step that actually runs
            (``guardrails``, ``rewriting``, ``retrieving``, ``reranking``,
            ``generating``) so clients can render a live progress trace.
            The stream terminates with a ``{"type": "done", "answer": ...,
            "sources": [...], "confidence": ...}`` event — or, when the input
            guardrail check blocks the question, a ``{"type": "blocked",
            "message": ..., "reason": ...}`` event with no LLM call.

        Raises:
            RAGQueryError: On any failure during the pipeline.
        """
        k = top_k or self.DEFAULT_TOP_K

        try:
            # 0. Prompt version selection (settings + optional A/B knob).
            selected_version = self._select_prompt_version()

            # 0. Guardrails: input check (pre-retrieval, optional). Never
            # crashes the pipeline — on any failure we log and pass through.
            if self._guardrail_manager is not None:
                yield self._stage_event(
                    "guardrails",
                    "Checking your question for safety",
                )
            input_check = self._check_input(question)
            if input_check.get("blocked", False):
                logger.info("Stream query blocked by input guardrails")
                yield {
                    "type": "blocked",
                    "message": self.BLOCKED_MESSAGE,
                    "reason": input_check,
                }
                return

            # 1. Embed the question
            base_collection = self._settings.CHROMA_COLLECTION_NAME
            collection = base_collection

            yield self._stage_event(
                "retrieving",
                "Searching your documents for relevant passages",
            )
            query_embedding = await self._embedding.embed(question)
            if getattr(self._settings, "ENABLE_HYBRID_SEARCH", False):
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


            # rerank
            if self._reranker is not None and chunks:
                yield self._stage_event(
                    "reranking",
                    "Reranking results by relevance",
                )
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
                done_event: dict[str, object] = {
                    "type": "done",
                    "answer": message,
                    "sources": [],
                    "confidence": 0.0,
                    "prompt_version": selected_version,
                }
                if self._guardrail_manager is not None:
                    done_event["guardrails"] = {
                        "input": input_check,
                        "output": {},
                    }
                yield done_event
                return

            # 3. Build prompt with context
            prompt = self._build_prompt(question, chunks, selected_version)

            # 4. Stream answer (accumulated for the post-generation check)
            answer_parts: list[str] = []
            yield self._stage_event(
                "generating",
                "Drafting the answer from the retrieved context",
            )
            async for chunk in self._llm.generate_stream(prompt):
                answer_parts.append(chunk)
                yield chunk

            # 5. Finalise: sources + confidence come from the very chunks the
            #    answer was generated from, so citations can never disagree
            #    with the streamed text. Guardrails (when enabled) add an
            #    extra output check on top.
            answer = "".join(answer_parts)
            done_event = {
                "type": "done",
                "answer": answer,
                "sources": self._format_sources(chunks),
                "confidence": self._compute_confidence(chunks),
                "prompt_version": selected_version,
            }
            if self._guardrail_manager is not None:
                done_event["guardrails"] = {
                    "input": input_check,
                    "output": self._check_output(answer, chunks),
                }
            yield done_event

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

    # ------------------------------------------------------------------
    # Guardrail helpers (optional — pass-through when no manager is wired)
    # ------------------------------------------------------------------

    def _check_input(self, question: str) -> dict[str, object]:
        """Run the input guardrail check without ever raising.

        Guardrails are best-effort: on any failure the check is logged and
        treated as a clean pass-through so the pipeline keeps running.

        Args:
            question: The user question to check.

        Returns:
            ``{"flagged": bool, "issues": list, "blocked": bool}``.
        """
        if self._guardrail_manager is None:
            return {"flagged": False, "issues": [], "blocked": False}
        try:
            return self._guardrail_manager.check_input(question)
        except Exception as exc:
            logger.warning("Input guardrail check failed: %s", exc)
            return {"flagged": False, "issues": [], "blocked": False}

    def _check_output(self, answer: str, chunks: list) -> dict[str, object]:
        """Run the output guardrail check without ever raising.

        Args:
            answer: The generated answer text.
            chunks: Retrieved chunks used as grounding context.

        Returns:
            ``{"flagged": bool, "issues": list, "groundedness": float}``.
        """
        if self._guardrail_manager is None:
            return {"flagged": False, "issues": [], "groundedness": 1.0}
        try:
            contexts = [chunk.content for chunk in chunks]
            return self._guardrail_manager.check_output(answer, contexts)
        except Exception as exc:
            logger.warning("Output guardrail check failed: %s", exc)
            return {"flagged": False, "issues": [], "groundedness": 1.0}

    def _finalize(
        self,
        result: dict,
        guardrail_metadata: dict[str, object] | None,
        answer: str | None = None,
        chunks: list | None = None,
        prompt_version: str | None = None,
    ) -> dict:
        """Merge guardrail results and the prompt version into the metadata.

        When neither guardrails nor a prompt version is supplied the
        result is returned untouched, preserving the previous pipeline
        behaviour exactly. When supplied, the output check runs if an
        answer and chunks are available, and the results are stored under
        ``metadata["guardrails"]`` and ``metadata["prompt_version"]``
        without dropping existing metadata keys (e.g. the structured-
        output ``"mode"`` key).

        Args:
            result:             The pipeline result dict.
            guardrail_metadata: In-progress guardrail metadata, or None.
            answer:             Generated answer; output check runs when set.
            chunks:             Retrieved chunks used as output-check context.
            prompt_version:     Selected system-prompt version id, or None.

        Returns:
            ``result`` with guardrail results / prompt version merged in
            when supplied.
        """
        if guardrail_metadata is None and prompt_version is None:
            return result
        if guardrail_metadata is not None and answer is not None and chunks is not None:
            output_check = self._check_output(answer, chunks)
            guardrail_metadata["output"] = output_check
        metadata = dict(result.get("metadata") or {})
        if prompt_version is not None:
            metadata["prompt_version"] = prompt_version
        if guardrail_metadata is not None:
            metadata["guardrails"] = guardrail_metadata
        result["metadata"] = metadata
        return result

    def _select_prompt_version(self) -> str:
        """Pick the system-prompt version from settings.

        ``PROMPT_VERSION`` is a typed ``str`` field, so it is always a
        non-empty string by construction — no runtime validation needed.
        """
        return self._settings.PROMPT_VERSION

    def _build_prompt(
        self, question: str, chunks: list, prompt_version: str | None = None
    ) -> str:
        """Build the RAG prompt with retrieved context and question.

        Args:
            question:       The user's question.
            chunks:         Retrieved text chunks for context.
            prompt_version: Version id whose template to use; when None
                            the version is selected from settings.

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

        if prompt_version is None:
            prompt_version = self._select_prompt_version()
        template = get_prompt(prompt_version)
        return template.format(
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
