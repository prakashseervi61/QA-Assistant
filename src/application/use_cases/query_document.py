"""Use case for querying documents via RAG with conversation history.

Orchestrates the full query pipeline:
  validate → manage conversation → retrieve → generate → persist
"""

import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message
from src.domain.interfaces.conversation_repository import ConversationRepository

logger = logging.getLogger(__name__)


class QueryDocumentError(Exception):
    """Raised when document querying fails."""


class ConversationNotFoundError(QueryDocumentError):
    """Raised when a referenced conversation does not exist."""


class QueryDocumentUseCase:
    """Use case for querying documents with conversation history.

    Responsibilities:
        - Create or load conversations
        - Persist user and assistant messages
        - Delegate retrieval-augmented generation to the RAG engine
        - Return structured results or stream them
    """

    def __init__(
        self,
        rag_engine: Any,
        conversation_repository: ConversationRepository,
    ) -> None:
        self._rag_engine = rag_engine
        self._conversation_repo = conversation_repository

    async def execute(
        self,
        question: str,
        conversation_id: str | None = None,
        top_k: int = 5,
    ) -> dict:
        """Execute a document query (non-streaming)."""
        self._validate_question(question)

        try:
            conversation = await self._resolve_conversation(conversation_id)
            resolved_id = str(conversation.id)
            logger.info(
                "Querying documents (conversation=%s, top_k=%d)", resolved_id, top_k
            )

            user_message = Message(role="user", content=question)
            await self._conversation_repo.add_message(conversation.id, user_message)

            try:
                rag_result = await self._rag_engine.query(
                    question=question, top_k=top_k
                )
            except Exception as exc:
                logger.error(
                    "RAG engine failed for %s: %s", resolved_id, exc, exc_info=True
                )
                raise QueryDocumentError(
                    f"RAG engine failed to process the query: {exc}"
                ) from exc

            answer = rag_result.get("answer", "")
            sources = rag_result.get("sources", [])
            confidence = rag_result.get("confidence", 0.0)

            assistant_message = Message(
                role="assistant", content=answer, sources=sources
            )
            await self._conversation_repo.add_message(
                conversation.id, assistant_message
            )
            await self._conversation_repo.save_conversation(conversation)

            return {
                "answer": answer,
                "sources": sources,
                "confidence": confidence,
                "conversation_id": resolved_id,
                "message_id": str(assistant_message.id),
            }

        except (ConversationNotFoundError, ValueError, QueryDocumentError):
            raise
        except Exception as exc:
            logger.error("Unexpected error in query_document: %s", exc, exc_info=True)
            raise QueryDocumentError(f"Failed to query documents: {exc}") from exc

    async def execute_stream(
        self,
        question: str,
        conversation_id: str | None = None,
        top_k: int = 5,
    ) -> AsyncIterator[dict]:
        """Execute a document query with streaming response."""
        self._validate_question(question)

        try:
            conversation = await self._resolve_conversation(conversation_id)
            resolved_id = str(conversation.id)
            logger.info(
                "Streaming query (conversation=%s, top_k=%d)", resolved_id, top_k
            )

            user_message = Message(role="user", content=question)
            await self._conversation_repo.add_message(conversation.id, user_message)

            full_answer_parts: list[str] = []
            try:
                async for chunk in self._rag_engine.query_stream(
                    question=question, top_k=top_k
                ):
                    full_answer_parts.append(chunk)
                    yield {"type": "chunk", "content": chunk}
            except Exception as exc:
                logger.error(
                    "RAG stream failed for %s: %s", resolved_id, exc, exc_info=True
                )
                raise QueryDocumentError(f"RAG engine stream failed: {exc}") from exc

            full_answer = "".join(full_answer_parts)

            try:
                rag_result = await self._rag_engine.query(
                    question=question, top_k=top_k
                )
            except Exception as exc:
                logger.warning(
                    "Failed to fetch sources after stream for %s: %s", resolved_id, exc
                )
                rag_result = {}

            sources = rag_result.get("sources", [])
            confidence = rag_result.get("confidence", 0.0)

            assistant_message = Message(
                role="assistant", content=full_answer, sources=sources
            )
            await self._conversation_repo.add_message(
                conversation.id, assistant_message
            )
            await self._conversation_repo.save_conversation(conversation)

            yield {
                "type": "done",
                "answer": full_answer,
                "sources": sources,
                "confidence": confidence,
                "conversation_id": resolved_id,
                "message_id": str(assistant_message.id),
            }

        except (ConversationNotFoundError, ValueError, QueryDocumentError):
            raise
        except Exception as exc:
            logger.error(
                "Unexpected error in query_document stream: %s", exc, exc_info=True
            )
            raise QueryDocumentError(
                f"Failed to stream query documents: {exc}"
            ) from exc

    @staticmethod
    def _validate_question(question: str) -> None:
        if not question or not question.strip():
            raise ValueError("Question must not be empty.")

    async def _resolve_conversation(self, conversation_id: str | None) -> Conversation:
        if conversation_id is None:
            conversation = Conversation(id=uuid4(), title="")
            await self._conversation_repo.save_conversation(conversation)
            logger.info("Created new conversation %s", conversation.id)
            return conversation

        try:
            conv_uuid = UUID(conversation_id)
        except ValueError:
            raise ValueError(f"Invalid conversation ID format: '{conversation_id}'")

        try:
            conversation = await self._conversation_repo.get_conversation(conv_uuid)
        except KeyError:
            raise ConversationNotFoundError(
                f"Conversation not found: {conversation_id}"
            )

        logger.debug("Loaded existing conversation %s", conv_uuid)
        return conversation
