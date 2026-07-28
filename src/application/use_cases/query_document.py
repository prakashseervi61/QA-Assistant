"""Use case for querying documents via RAG with conversation history.

Orchestrates the full query pipeline:
  validate → manage conversation → retrieve → generate → persist

This use case sits between the API layer and the RAG engine,
handling conversation lifecycle and message persistence.
"""

import logging
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message
from src.domain.interfaces.conversation_repository import ConversationRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class QueryDocumentError(Exception):
    """Raised when document querying fails."""


class ConversationNotFoundError(QueryDocumentError):
    """Raised when a referenced conversation does not exist."""


# ---------------------------------------------------------------------------
# RAG Engine protocol (concrete class created by another agent)
# ---------------------------------------------------------------------------

@runtime_checkable
class RAGEngineProtocol(Protocol):
    """Minimal protocol for the RAG engine dependency.

    This allows the use case to depend on an interface rather than a
    concrete class, keeping the dependency direction clean even before
    the full RAG engine is implemented.
    """

    async def query(self, question: str, top_k: int = 5) -> dict:
        """Embed → retrieve → generate.  Returns answer, sources, metadata."""
        ...

    async def query_stream(
        self, question: str, top_k: int = 5
    ) -> AsyncIterator[str]:
        """Same as query but yields answer chunks for streaming."""
        ...


# ---------------------------------------------------------------------------
# Use case
# ---------------------------------------------------------------------------

class QueryDocumentUseCase:
    """Use case for querying documents with conversation history.

    Responsibilities:
        - Create or load conversations
        - Persist user and assistant messages
        - Delegate retrieval-augmented generation to the RAG engine
        - Return structured results (answer, sources, metadata)
        - Support streaming responses

    This class follows the Clean Architecture use-case pattern:
    it depends only on domain interfaces, never on infrastructure.
    """

    def __init__(
        self,
        rag_engine: RAGEngineProtocol,
        conversation_repository: ConversationRepository,
    ) -> None:
        self._rag_engine = rag_engine
        self._conversation_repo = conversation_repository

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        question: str,
        conversation_id: str | None = None,
        top_k: int = 5,
    ) -> dict:
        """Execute a document query (non-streaming).

        Args:
            question:         The user's natural-language question.
            conversation_id:  Optional UUID string for an existing conversation.
                              When *None* a new conversation is created.
            top_k:            Number of source chunks to retrieve (1–20).

        Returns:
            A dict with keys:
                - answer          (str)   – generated answer
                - sources         (list)  – source chunks with scores
                - confidence      (float) – average relevance score
                - conversation_id (str)   – ID of the conversation
                - message_id      (str)   – ID of the assistant message

        Raises:
            QueryDocumentError:           On any failure during the pipeline.
            ConversationNotFoundError:    If *conversation_id* references a
                                          conversation that does not exist.
            ValueError:                   If *question* is empty.
        """
        self._validate_question(question)

        try:
            # ----------------------------------------------------------
            # 1. Resolve or create conversation
            # ----------------------------------------------------------
            conversation = await self._resolve_conversation(conversation_id)
            resolved_id = str(conversation.id)

            logger.info(
                "Querying documents (conversation=%s, top_k=%d)",
                resolved_id,
                top_k,
            )

            # ----------------------------------------------------------
            # 2. Persist the user message
            # ----------------------------------------------------------
            user_message = Message(role="user", content=question)
            await self._conversation_repo.add_message(
                conversation.id, user_message
            )
            logger.debug("Saved user message to conversation %s", resolved_id)

            # ----------------------------------------------------------
            # 3. Query the RAG engine
            # ----------------------------------------------------------
            try:
                rag_result = await self._rag_engine.query(
                    question=question, top_k=top_k
                )
            except Exception as exc:
                logger.error(
                    "RAG engine failed for conversation %s: %s",
                    resolved_id,
                    exc,
                    exc_info=True,
                )
                raise QueryDocumentError(
                    f"RAG engine failed to process the query: {exc}"
                ) from exc

            answer = rag_result.get("answer", "")
            sources = rag_result.get("sources", [])
            confidence = rag_result.get("confidence", 0.0)

            # ----------------------------------------------------------
            # 4. Persist the assistant message
            # ----------------------------------------------------------
            assistant_message = Message(
                role="assistant",
                content=answer,
                sources=sources,
            )
            await self._conversation_repo.add_message(
                conversation.id, assistant_message
            )
            logger.debug("Saved assistant message to conversation %s", resolved_id)

            # ----------------------------------------------------------
            # 5. Save updated conversation
            # ----------------------------------------------------------
            await self._conversation_repo.save_conversation(conversation)

            logger.info(
                "Query completed (conversation=%s, sources=%d, confidence=%.2f)",
                resolved_id,
                len(sources),
                confidence,
            )

            # ----------------------------------------------------------
            # 6. Return structured result
            # ----------------------------------------------------------
            return {
                "answer": answer,
                "sources": sources,
                "confidence": confidence,
                "conversation_id": resolved_id,
                "message_id": str(assistant_message.id),
            }

        except (ConversationNotFoundError, ValueError):
            raise
        except QueryDocumentError:
            raise
        except Exception as exc:
            logger.error(
                "Unexpected error in query_document: %s", exc, exc_info=True
            )
            raise QueryDocumentError(
                f"Failed to query documents: {exc}"
            ) from exc

    async def execute_stream(
        self,
        question: str,
        conversation_id: str | None = None,
        top_k: int = 5,
    ) -> AsyncIterator[dict]:
        """Execute a document query with streaming response.

        Yields dicts so callers can distinguish between intermediate
        chunks and the final summary:

        * **Chunk events** (during streaming):
          ``{"type": "chunk", "content": "<token>"}``

        * **Final event** (after streaming completes):
          ``{"type": "done", "answer": "<full>", "sources": [...],
            "confidence": 0.0, "conversation_id": "...",
            "message_id": "..."}``

        Args:
            question:         The user's natural-language question.
            conversation_id:  Optional UUID string for an existing conversation.
            top_k:            Number of source chunks to retrieve.

        Raises:
            QueryDocumentError:        On any failure during the pipeline.
            ConversationNotFoundError: If the conversation does not exist.
            ValueError:                If *question* is empty.
        """
        self._validate_question(question)

        try:
            # ----------------------------------------------------------
            # 1. Resolve or create conversation
            # ----------------------------------------------------------
            conversation = await self._resolve_conversation(conversation_id)
            resolved_id = str(conversation.id)

            logger.info(
                "Streaming query (conversation=%s, top_k=%d)",
                resolved_id,
                top_k,
            )

            # ----------------------------------------------------------
            # 2. Persist the user message
            # ----------------------------------------------------------
            user_message = Message(role="user", content=question)
            await self._conversation_repo.add_message(
                conversation.id, user_message
            )
            logger.debug("Saved user message to conversation %s", resolved_id)

            # ----------------------------------------------------------
            # 3. Stream the RAG engine response
            # ----------------------------------------------------------
            full_answer_parts: list[str] = []

            try:
                async for chunk in self._rag_engine.query_stream(
                    question=question, top_k=top_k
                ):
                    full_answer_parts.append(chunk)
                    yield {"type": "chunk", "content": chunk}
            except Exception as exc:
                logger.error(
                    "RAG stream failed for conversation %s: %s",
                    resolved_id,
                    exc,
                    exc_info=True,
                )
                raise QueryDocumentError(
                    f"RAG engine stream failed: {exc}"
                ) from exc

            full_answer = "".join(full_answer_parts)

            # ----------------------------------------------------------
            # 4. Obtain sources (separate call after streaming)
            # ----------------------------------------------------------
            # The stream only yields the generated text.  We do a standard
            # query to retrieve sources and confidence metadata.  This is
            # acceptable because source retrieval is cheap compared to
            # generation.
            try:
                rag_result = await self._rag_engine.query(
                    question=question, top_k=top_k
                )
            except Exception as exc:
                # If source retrieval fails after a successful stream,
                # we still persist what we have — just without sources.
                logger.warning(
                    "Failed to fetch sources after stream for %s: %s",
                    resolved_id,
                    exc,
                )
                rag_result = {}

            sources = rag_result.get("sources", [])
            confidence = rag_result.get("confidence", 0.0)

            # ----------------------------------------------------------
            # 5. Persist the assistant message with full response
            # ----------------------------------------------------------
            assistant_message = Message(
                role="assistant",
                content=full_answer,
                sources=sources,
            )
            await self._conversation_repo.add_message(
                conversation.id, assistant_message
            )
            await self._conversation_repo.save_conversation(conversation)

            logger.info(
                "Stream completed (conversation=%s, sources=%d)",
                resolved_id,
                len(sources),
            )

            # ----------------------------------------------------------
            # 6. Yield the final summary event
            # ----------------------------------------------------------
            yield {
                "type": "done",
                "answer": full_answer,
                "sources": sources,
                "confidence": confidence,
                "conversation_id": resolved_id,
                "message_id": str(assistant_message.id),
            }

        except (ConversationNotFoundError, ValueError):
            raise
        except QueryDocumentError:
            raise
        except Exception as exc:
            logger.error(
                "Unexpected error in query_document stream: %s",
                exc,
                exc_info=True,
            )
            raise QueryDocumentError(
                f"Failed to stream query documents: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_question(question: str) -> None:
        """Ensure the question is non-empty after stripping whitespace."""
        if not question or not question.strip():
            raise ValueError("Question must not be empty.")

    async def _resolve_conversation(
        self, conversation_id: str | None
    ) -> Conversation:
        """Load an existing conversation or create a new one.

        Args:
            conversation_id: UUID string or *None*.

        Returns:
            The loaded or newly created :class:`Conversation`.

        Raises:
            ConversationNotFoundError: If the ID was provided but does
                not correspond to an existing conversation.
        """
        if conversation_id is None:
            conversation = Conversation(
                id=uuid4(),
                title="",
            )
            await self._conversation_repo.save_conversation(conversation)
            logger.info("Created new conversation %s", conversation.id)
            return conversation

        # Parse the UUID
        try:
            conv_uuid = UUID(conversation_id)
        except ValueError:
            raise ValueError(
                f"Invalid conversation ID format: '{conversation_id}'"
            )

        try:
            conversation = await self._conversation_repo.get_conversation(
                conv_uuid
            )
        except KeyError:
            raise ConversationNotFoundError(
                f"Conversation not found: {conversation_id}"
            )

        logger.debug("Loaded existing conversation %s", conv_uuid)
        return conversation
