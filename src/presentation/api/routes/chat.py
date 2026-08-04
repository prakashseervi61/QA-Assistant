"""Chat API routes for document querying and conversation management."""

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.application.dto.requests import QueryRequest
from src.application.dto.responses import (
    ConversationResponse,
    MessageResponse,
    QueryResponse,
    SourceChunk,
)
from src.application.use_cases.conversation import (
    GetConversationUseCase,
    ListConversationsUseCase,
)
from src.application.use_cases.query_document import (
    ConversationNotFoundError,
    QueryDocumentError,
    QueryDocumentUseCase,
)
from src.domain.interfaces.llm_provider import LLMQuotaExceededError

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency placeholder — will be wired up in app.py factory
# ---------------------------------------------------------------------------

_query_use_case: QueryDocumentUseCase | None = None


def set_query_use_case(use_case: QueryDocumentUseCase) -> None:
    """Register the QueryDocumentUseCase dependency at startup."""
    global _query_use_case
    _query_use_case = use_case


def get_query_use_case() -> QueryDocumentUseCase:
    """FastAPI dependency that returns the injected use case."""
    if _query_use_case is None:
        raise HTTPException(
            status_code=503,
            detail="Query service not initialised. Check server configuration.",
        )
    return _query_use_case


_conversation_list_use_case: ListConversationsUseCase | None = None


def set_conversation_list_use_case(use_case: ListConversationsUseCase) -> None:
    """Register the ListConversationsUseCase dependency at startup."""
    global _conversation_list_use_case
    _conversation_list_use_case = use_case


def get_conversation_list_use_case() -> ListConversationsUseCase:
    """FastAPI dependency that returns the injected use case."""
    if _conversation_list_use_case is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Conversation list service not initialised. "
                "Check server configuration."
            ),
        )
    return _conversation_list_use_case


_conversation_get_use_case: GetConversationUseCase | None = None


def set_conversation_get_use_case(use_case: GetConversationUseCase) -> None:
    """Register the GetConversationUseCase dependency at startup."""
    global _conversation_get_use_case
    _conversation_get_use_case = use_case


def get_conversation_get_use_case() -> GetConversationUseCase:
    """FastAPI dependency that returns the injected use case."""
    if _conversation_get_use_case is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Conversation get service not initialised. "
                "Check server configuration."
            ),
        )
    return _conversation_get_use_case


def _to_source_chunks(sources: list[dict]) -> list[SourceChunk]:
    """Map raw source dicts to SourceChunk DTOs."""
    return [
        SourceChunk(
            content=s.get("content", ""),
            metadata=s.get("metadata", {}),
            score=s.get("score", s.get("metadata", {}).get("score", 0.0)),
            chunk_index=s.get(
                "chunk_index", s.get("metadata", {}).get("chunk_index", 0)
            ),
        )
        for s in sources
    ]


def _to_iso(dt: datetime) -> str:
    """Format a datetime as an ISO 8601 string."""
    return dt.isoformat()


# ---------------------------------------------------------------------------
# POST /query — non-streaming document query
# ---------------------------------------------------------------------------


@router.post("/query", response_model=QueryResponse)
async def query_documents(
    request: QueryRequest,
    use_case: QueryDocumentUseCase = Depends(get_query_use_case),
) -> QueryResponse:
    """Ask a question about the ingested documents.

    Returns the answer, relevant source chunks, and confidence score.
    Optionally continues an existing conversation via ``conversation_id``.
    """
    try:
        result = await use_case.execute(
            question=request.question,
            conversation_id=request.conversation_id,
            top_k=request.top_k,
            metadata_filter=request.metadata_filter,
        )

        return QueryResponse(
            answer=result["answer"],
            sources=_to_source_chunks(result.get("sources", [])),
            confidence=result.get("confidence", 0.0),
            conversation_id=result.get("conversation_id"),
            message_id=result.get("message_id"),
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except LLMQuotaExceededError as exc:
        logger.warning("LLM quota exceeded: %s", exc)
        raise HTTPException(status_code=429, detail=str(exc))
    except QueryDocumentError as exc:
        logger.error("Query failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# POST /query/stream — streaming document query (Server-Sent Events)
# ---------------------------------------------------------------------------


async def _stream_events(
    use_case: QueryDocumentUseCase,
    request: QueryRequest,
) -> AsyncIterator[str]:
    """Yield Server-Sent Event strings from the streaming query."""
    try:
        async for event in use_case.execute_stream(
            question=request.question,
            conversation_id=request.conversation_id,
            top_k=request.top_k,
            metadata_filter=request.metadata_filter,
        ):
            yield f"data: {json.dumps(event)}\n\n"
    except (
        QueryDocumentError,
        ValueError,
        ConversationNotFoundError,
        LLMQuotaExceededError,
    ) as exc:
        error_event = {"type": "error", "message": str(exc)}
        yield f"data: {json.dumps(error_event)}\n\n"
    finally:
        yield "data: [DONE]\n\n"


@router.post("/query/stream")
async def query_documents_stream(
    request: QueryRequest,
    use_case: QueryDocumentUseCase = Depends(get_query_use_case),
) -> StreamingResponse:
    """Stream a document query response using Server-Sent Events.

    Each event is a JSON object with a ``type`` field:
    - ``chunk``  — incremental answer text
    - ``done``   — final summary with sources and metadata
    - ``error``  — error message

    Contract: even when the LLM provider raises a quota/rate-limit error
    (``LLMQuotaExceededError``), the response is still HTTP 200 with
    ``text/event-stream`` and emits ``{"type": "error", "message": ...}``
    followed by a ``[DONE]`` event, so streaming clients always see a
    well-formed termination.
    """
    return StreamingResponse(
        _stream_events(use_case, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# GET /conversations — list recent conversations
# ---------------------------------------------------------------------------


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    use_case: ListConversationsUseCase = Depends(get_conversation_list_use_case),
) -> list[ConversationResponse]:
    """Return the most recent conversations (newest first).

    Conversations without any messages are filtered out by the use case.
    """
    conversations = await use_case.execute(limit=10)
    return [
        ConversationResponse(
            id=str(c.id),
            title=c.title,
            created_at=_to_iso(c.created_at),
            updated_at=_to_iso(c.updated_at or c.created_at),
            message_count=len(c.messages),
        )
        for c in conversations
    ]


# ---------------------------------------------------------------------------
# GET /conversations/{conversation_id} — messages in a conversation
# ---------------------------------------------------------------------------


@router.get(
    "/conversations/{conversation_id}",
    response_model=list[MessageResponse],
)
async def get_conversation(
    conversation_id: str,
    use_case: GetConversationUseCase = Depends(get_conversation_get_use_case),
) -> list[MessageResponse]:
    """Return all messages in a conversation, ordered chronologically.

    Raises:
        400: If conversation_id is not a valid UUID.
        404: If the conversation does not exist.
    """
    try:
        messages = await use_case.execute(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return [
        MessageResponse(
            id=str(m.id),
            role=m.role,
            content=m.content,
            sources=_to_source_chunks(m.sources),
            created_at=_to_iso(m.created_at),
        )
        for m in messages
    ]
