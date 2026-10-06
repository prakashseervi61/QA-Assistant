"""Settings API routes — runtime config view, user API key, and data export.

The API-key routes are the only place a credential enters the system from the
browser. Two rules hold throughout this module:

1. A stored key is never returned. Reads expose only a mask and which source
   is active.
2. The key is never logged. Error paths log the exception, not the payload.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.application.dto.responses import DocumentInfo
from src.domain.interfaces.conversation_repository import ConversationRepository
from src.domain.interfaces.secret_store import SecretStore
from src.domain.interfaces.vector_store import VectorStore
from src.infrastructure.config.settings import Settings, get_settings
from src.infrastructure.llm.api_key_resolver import (
    SOURCE_ENV,
    SOURCE_NONE,
    SOURCE_USER,
    ApiKeyResolver,
    mask_api_key,
)
from src.presentation.api.dependencies import Registry

logger = logging.getLogger(__name__)

router = APIRouter()

_resolver: Registry[ApiKeyResolver] = Registry("API key")
_store: Registry[SecretStore] = Registry("Secret store")
_vector_store: Registry[VectorStore] = Registry("Settings vector store")
_conversations: Registry[ConversationRepository] = Registry(
    "Settings conversation repo"
)

# Google AI Studio keys are ~39 chars starting with "AIza", but the exact shape
# is Google's business and could change. Validate only what is certainly true of
# any credential, so a future key format is not rejected.
_MIN_KEY_LENGTH = 8
_MAX_KEY_LENGTH = 200


def configure(
    resolver: ApiKeyResolver,
    store: SecretStore,
    vector_store: VectorStore,
    conversation_repository: ConversationRepository,
) -> None:
    """Register shared dependencies at startup."""
    _resolver.set(resolver)
    _store.set(store)
    _vector_store.set(vector_store)
    _conversations.set(conversation_repository)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ApiKeyStatus(BaseModel):
    """What the UI needs to show about the credential — never the credential."""

    configured: bool
    source: str = Field(description="One of 'user', 'env', or 'none'.")
    masked: str | None = None


class ApiKeyUpdate(BaseModel):
    """Request body for storing a user-supplied API key."""

    api_key: str = Field(..., min_length=_MIN_KEY_LENGTH, max_length=_MAX_KEY_LENGTH)

    @field_validator("api_key")
    @classmethod
    def strip_and_validate(cls, v: str) -> str:
        """Trim the value and reject embedded whitespace.

        A key with a stray space is always a paste accident, and passing it
        through would produce an opaque 401 from Google rather than an
        actionable message here.
        """
        stripped = v.strip()
        if not stripped:
            raise ValueError("API key cannot be empty.")
        if any(ch.isspace() for ch in stripped):
            raise ValueError("API key cannot contain whitespace.")
        return stripped


class AppConfigResponse(BaseModel):
    """Non-secret runtime configuration for display in Settings."""

    app_name: str
    version: str
    llm_provider: str
    llm_model: str
    embedding_provider: str
    embedding_model: str
    enable_reranking: bool
    enable_hybrid_search: bool
    enable_semantic_chunking: bool
    enable_incremental_ingestion: bool
    enable_guardrails: bool
    guardrail_block_violations: bool
    enable_usage_tracking: bool
    max_file_size_mb: int
    history_db_path: str
    chroma_persist_dir: str
    secrets_file_path: str
    history_db_bytes: int
    document_count: int
    chunk_count: int


class ExportResponse(BaseModel):
    """A portable snapshot of everything the app holds."""

    exported_at: str
    app_version: str
    documents: list[DocumentInfo]
    conversations: list[dict]


# ---------------------------------------------------------------------------
# GET /settings/api-key — current credential status
# ---------------------------------------------------------------------------


@router.get("/settings/api-key", response_model=ApiKeyStatus)
async def get_api_key_status() -> ApiKeyStatus:
    """Report whether a key is configured and where it came from.

    Returns a mask only. The stored key is never part of this response.
    """
    resolver = _resolver.get()
    active = resolver.resolve()
    return ApiKeyStatus(
        configured=bool(active),
        source=resolver.source(),
        masked=mask_api_key(active),
    )


# ---------------------------------------------------------------------------
# PUT /settings/api-key — store a user-supplied key
# ---------------------------------------------------------------------------


@router.put("/settings/api-key", response_model=ApiKeyStatus)
async def put_api_key(payload: ApiKeyUpdate) -> ApiKeyStatus:
    """Store a user-supplied API key, taking effect on the next request.

    Overrides any previously stored key and the ``.env`` value. The response
    echoes only a mask.
    """
    store = _store.get()
    store.set_api_key(payload.api_key)
    # Deliberately not logging the value.
    logger.info("API key updated from the Settings page")
    return ApiKeyStatus(
        configured=True,
        source=SOURCE_USER,
        masked=mask_api_key(payload.api_key),
    )


# ---------------------------------------------------------------------------
# DELETE /settings/api-key — forget the user key, fall back to .env
# ---------------------------------------------------------------------------


@router.delete("/settings/api-key", response_model=ApiKeyStatus)
async def delete_api_key() -> ApiKeyStatus:
    """Remove the stored key and fall back to the environment value."""
    store = _store.get()
    store.clear_api_key()
    resolver = _resolver.get()
    active = resolver.resolve()
    source = SOURCE_ENV if active else SOURCE_NONE
    return ApiKeyStatus(
        configured=bool(active), source=source, masked=mask_api_key(active)
    )


# ---------------------------------------------------------------------------
# GET /settings — non-secret configuration
# ---------------------------------------------------------------------------


def _directory_size(path: Path) -> int:
    """Total bytes of a file, or of a directory tree. 0 when absent."""
    try:
        if path.is_file():
            return path.stat().st_size
        if path.is_dir():
            return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    except OSError:
        logger.warning("Could not measure size of %s", path, exc_info=True)
    return 0


@router.get("/settings", response_model=AppConfigResponse)
async def get_app_config(
    settings: Settings = Depends(get_settings),
) -> AppConfigResponse:
    """Return non-secret configuration plus on-disk storage figures.

    Deliberately an allow-list: adding a field to ``Settings`` must not
    silently publish it here, which is how secrets leak into config endpoints.
    """
    vector_store = _vector_store.get()
    collection = settings.CHROMA_COLLECTION_NAME

    try:
        docs = await vector_store.list_documents(collection)
        chunk_count = await vector_store.get_collection_count(collection)
    except Exception as exc:
        logger.error("Could not read vector store stats: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Could not read storage stats.")

    return AppConfigResponse(
        app_name=settings.APP_NAME,
        version="0.1.0",
        llm_provider=settings.LLM_PROVIDER,
        llm_model=settings.GEMINI_MODEL,
        embedding_provider=settings.EMBEDDING_PROVIDER,
        embedding_model=settings.HUGGINGFACE_MODEL,
        enable_reranking=settings.ENABLE_RERANKING,
        enable_hybrid_search=settings.ENABLE_HYBRID_SEARCH,
        enable_semantic_chunking=settings.ENABLE_SEMANTIC_CHUNKING,
        enable_incremental_ingestion=settings.ENABLE_INCREMENTAL_INGESTION,
        enable_guardrails=settings.ENABLE_GUARDRAILS,
        guardrail_block_violations=settings.GUARDRAIL_BLOCK_VIOLATIONS,
        enable_usage_tracking=settings.ENABLE_USAGE_TRACKING,
        max_file_size_mb=settings.MAX_FILE_SIZE_MB,
        history_db_path=settings.HISTORY_DB_PATH,
        chroma_persist_dir=settings.CHROMA_PERSIST_DIR,
        secrets_file_path=settings.SECRETS_FILE_PATH,
        history_db_bytes=_directory_size(Path(settings.HISTORY_DB_PATH)),
        document_count=len(docs),
        chunk_count=chunk_count,
    )


# ---------------------------------------------------------------------------
# GET /export — portable snapshot of documents and conversations
# ---------------------------------------------------------------------------


@router.get("/export", response_model=ExportResponse)
async def export_data(settings: Settings = Depends(get_settings)) -> ExportResponse:
    """Return every document and conversation as one JSON payload.

    Exists so the Danger Zone can offer "export first" — per the convention
    that a destructive action should never be the only way out.
    """
    vector_store = _vector_store.get()
    repo = _conversations.get()

    try:
        docs = await vector_store.list_documents(settings.CHROMA_COLLECTION_NAME)
    except Exception as exc:
        logger.error("Export: could not list documents: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Could not export documents.")

    try:
        # limit=None is the full history, not the default page.
        conversations = await repo.list_conversations(limit=None)
    except Exception as exc:
        logger.error("Export: could not list conversations: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Could not export conversations.")

    payload: list[dict] = []
    for conversation in conversations:
        messages = await repo.get_messages(conversation.id)
        payload.append(
            {
                "id": str(conversation.id),
                "title": conversation.title,
                "created_at": conversation.created_at.isoformat(),
                "updated_at": (
                    conversation.updated_at or conversation.created_at
                ).isoformat(),
                "messages": [
                    {
                        "id": str(m.id),
                        "role": m.role,
                        "content": m.content,
                        "created_at": m.created_at.isoformat(),
                        "sources": m.sources or [],
                    }
                    for m in messages
                ],
            }
        )

    return ExportResponse(
        exported_at=datetime.now(UTC).isoformat(),
        app_version="0.1.0",
        documents=[
            DocumentInfo(
                id=doc["document_id"],
                filename=doc["filename"],
                content_type=doc["file_type"],
                file_size=doc["file_size"],
                chunk_count=doc["chunk_count"],
                created_at=doc["created_at"],
            )
            for doc in docs
        ],
        conversations=payload,
    )
