"""Chat API routes for document querying and conversation management."""

import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
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
from src.domain.interfaces.conversation_repository import ConversationRepository
from src.domain.interfaces.llm_provider import LLMQuotaExceededError
from src.presentation.api.dependencies import Registry

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Startup dependencies — registered by app._wire_dependencies
# ---------------------------------------------------------------------------

_query_use_case: Registry[QueryDocumentUseCase] = Registry("Query")


def set_query_use_case(use_case: QueryDocumentUseCase) -> None:
    """Register the QueryDocumentUseCase dependency at startup."""
    _query_use_case.set(use_case)


def get_query_use_case() -> QueryDocumentUseCase:
    """FastAPI dependency that returns the injected use case."""
    return _query_use_case.get()


# ponytail: the list/get/delete conversation "use cases" were one-method
# wrappers around the repository (UUID parse + KeyError mapping + limit
# pass-through). Fold that thin validation into the routes and depend on
# the ConversationRepository directly.
_conversation_repository: Registry[ConversationRepository] = Registry(
    "Conversation repo"
)


def set_conversation_repository(repository: ConversationRepository) -> None:
    """Register the ConversationRepository dependency at startup."""
    _conversation_repository.set(repository)


def get_conversation_repository() -> ConversationRepository:
    """FastAPI dependency that returns the injected repository."""
    return _conversation_repository.get()


def _parse_conversation_id(conversation_id: str) -> UUID:
    """Parse a conversation UUID or raise an HTTP 400."""
    try:
        return UUID(conversation_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid conversation ID format: '{conversation_id}'",
        )


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
        # Quota guidance is genuinely useful to the local user, and the API is
        # bound to loopback, so this text never leaves the machine.
        logger.warning("LLM quota exceeded: %s", exc)
        raise HTTPException(status_code=429, detail=str(exc))
    except QueryDocumentError:
        # QueryDocumentError already wraps a low-level provider/vector-store
        # message, which can carry absolute paths or SDK internals. Log the
        # detail, return something stable.
        logger.error("Query failed", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="The query could not be completed. See the server logs.",
        )


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
    except (ValueError, ConversationNotFoundError, LLMQuotaExceededError) as exc:
        # Validation and quota text is safe (and useful) to show the user.
        error_event = {"type": "error", "message": str(exc)}
        yield f"data: {json.dumps(error_event)}\n\n"
    except QueryDocumentError:
        # Wraps a provider/vector-store message that may carry absolute paths
        # or SDK internals — log it, send something stable.
        logger.error("Streaming query failed", exc_info=True)
        error_event = {
            "type": "error",
            "message": ("The query could not be completed. See the server logs."),
        }
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
    limit: int = Query(
        default=200,
        ge=1,
        le=1000,
        description="Maximum conversations to return.",
    ),
    conversation_repository: ConversationRepository = Depends(
        get_conversation_repository
    ),
) -> list[ConversationResponse]:
    """Return conversations, newest first.

    Conversations without any messages are filtered out. The History view
    asks for a generous limit so the whole log is visible.
    """
    conversations = await conversation_repository.list_conversations(limit)
    conversations = [c for c in conversations if c.messages]
    return [
        ConversationResponse(
            id=str(c.id),
            title=c.title,
            created_at=c.created_at.isoformat(),
            updated_at=(c.updated_at or c.created_at).isoformat(),
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
    conversation_repository: ConversationRepository = Depends(
        get_conversation_repository
    ),
) -> list[MessageResponse]:
    """Return all messages in a conversation, ordered chronologically.

    Raises:
        400: If conversation_id is not a valid UUID.
        404: If the conversation does not exist.
    """
    conv_uuid = _parse_conversation_id(conversation_id)
    try:
        messages = await conversation_repository.get_messages(conv_uuid)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Conversation not found: {conversation_id}"
        )
    return [
        MessageResponse(
            id=str(m.id),
            role=m.role,
            content=m.content,
            sources=_to_source_chunks(m.sources),
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


# ---------------------------------------------------------------------------
# DELETE /conversations/{conversation_id} — remove a conversation from history
# ---------------------------------------------------------------------------


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    conversation_repository: ConversationRepository = Depends(
        get_conversation_repository
    ),
) -> dict:
    """Permanently delete a conversation and all of its messages.

    Returns a small JSON body rather than 204 so the client's DELETE helper,
    which always parses JSON, keeps working.

    Raises:
        400: If conversation_id is not a valid UUID.
        404: If no conversation with that id exists.
    """
    conv_uuid = _parse_conversation_id(conversation_id)
    deleted = await conversation_repository.delete_conversation(conv_uuid)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Conversation not found: {conversation_id}"
        )
    return {"deleted": True, "id": conversation_id}
