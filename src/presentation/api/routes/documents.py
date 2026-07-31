"""Document management API routes — upload, list, delete."""

import logging
import os

from fastapi import APIRouter, File, HTTPException, UploadFile

from src.application.dto.responses import (
    DocumentInfo,
    DocumentListResponse,
    IngestResponse,
)
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.interfaces.vector_store import VectorStore
from src.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# Injected at startup by app.py so upload/list/delete share one ChromaStore
_vector_store: VectorStore | None = None
_embedding_provider: EmbeddingProvider | None = None


def configure(vector_store: VectorStore, embedding_provider: EmbeddingProvider) -> None:
    """Register shared infrastructure dependencies at startup."""
    global _vector_store, _embedding_provider
    _vector_store = vector_store
    _embedding_provider = embedding_provider


def _get_dependencies() -> tuple[VectorStore, EmbeddingProvider]:
    """Return the injected dependencies or raise a 503 if not wired."""
    if _vector_store is None or _embedding_provider is None:
        raise HTTPException(
            status_code=503,
            detail="Document service not initialised. Check server configuration.",
        )
    return _vector_store, _embedding_provider


# ---------------------------------------------------------------------------
# POST /documents/upload — upload and ingest a document
# ---------------------------------------------------------------------------


@router.post("/documents/upload", response_model=IngestResponse)
async def upload_document(file: UploadFile = File(...)) -> IngestResponse:
    """Upload a document (PDF, DOCX, TXT) for ingestion into the vector store.

    The file is parsed, chunked, embedded, and stored in ChromaDB.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}"
            ),
        )

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file.")

        # Lazy import — use case depends on infra that may not be wired yet
        from src.application.use_cases.ingest_document import IngestDocumentUseCase
        from src.infrastructure.document_processing.parser_factory import create_parser
        from src.infrastructure.document_processing.text_splitter import TextSplitter

        vector_store, embedding_provider = _get_dependencies()

        use_case = IngestDocumentUseCase(
            parser=create_parser(ext),
            text_splitter=TextSplitter(),
            embedding_provider=embedding_provider,
            vector_store=vector_store,
        )

        result = await use_case.execute(file_content=content, filename=file.filename)

        return IngestResponse(
            document_id=result["document_id"],
            filename=result["filename"],
            chunk_count=result["chunk_count"],
            message=result["message"],
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Upload failed for '%s': %s", file.filename, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}")


# ---------------------------------------------------------------------------
# GET /documents — list all ingested documents
# ---------------------------------------------------------------------------


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents() -> DocumentListResponse:
    """Return a list of all ingested documents grouped by document ID."""
    vector_store, _ = _get_dependencies()
    settings = get_settings()

    try:
        docs = await vector_store.list_documents(settings.CHROMA_COLLECTION_NAME)
    except Exception as exc:
        logger.error("Failed to list documents: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {exc}")

    documents = [
        DocumentInfo(
            id=doc["document_id"],
            filename=doc["filename"],
            content_type=doc["file_type"],
            file_size=doc["file_size"],
            chunk_count=doc["chunk_count"],
            created_at=doc["created_at"],
        )
        for doc in docs
    ]
    return DocumentListResponse(documents=documents, total=len(documents))


# ---------------------------------------------------------------------------
# DELETE /documents/{document_id} — delete a document
# ---------------------------------------------------------------------------


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str) -> dict:
    """Delete a document and all of its chunks from the vector store."""
    vector_store, _ = _get_dependencies()
    settings = get_settings()

    try:
        await vector_store.delete_by_metadata(
            {"document_id": document_id},
            settings.CHROMA_COLLECTION_NAME,
        )
    except Exception as exc:
        logger.error(
            "Failed to delete document %s: %s", document_id, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to delete document: {exc}"
        )

    return {"message": f"Document {document_id} deleted successfully."}
