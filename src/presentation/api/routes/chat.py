"""Chat API routes for document querying and conversation management."""

import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.application.dto.requests import QueryRequest
from src.application.dto.responses import (
    ConversationResponse,
    MessageResponse,
    QueryResponse,
    SourceChunk,
)
from src.application.use_cases.query_document import (
    ConversationNotFoundError,
    QueryDocumentError,
    QueryDocumentUseCase,
)

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
        )

        sources = [
            SourceChunk(
                content=s.get("content", ""),
                metadata=s.get("metadata", {}),
                score=s.get("score", s.get("metadata", {}).get("score", 0.0)),
                chunk_index=s.get("chunk_index", s.get("metadata", {}).get("chunk_index", 0)),
            )
            for s in result.get("sources", [])
        ]

        return QueryResponse(
            answer=result["answer"],
            sources=sources,
            confidence=result.get("confidence", 0.0),
            conversation_id=result.get("conversation_id"),
            message_id=result.get("message_id"),
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
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
        ):
            yield f"data: {json.dumps(event)}\n\n"
    except (QueryDocumentError, ValueError, ConversationNotFoundError) as exc:
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
async def list_conversations() -> list[ConversationResponse]:
    """Return the most recent conversations (newest first).

    Note: Currently returns a placeholder until a conversation list
    use case is wired up.
    """
    # TODO: Wire up a ListConversationsUseCase
    return []


# ---------------------------------------------------------------------------
# GET /conversations/{conversation_id} — messages in a conversation
# ---------------------------------------------------------------------------


@router.get(
    "/conversations/{conversation_id}",
    response_model=list[MessageResponse],
)
async def get_conversation(conversation_id: str) -> list[MessageResponse]:
    """Return all messages in a conversation, ordered chronologically.

    Note: Currently returns a placeholder until a GetConversationUseCase
    is wired up.
    """
    # TODO: Wire up a GetConversationUseCase
    return []
