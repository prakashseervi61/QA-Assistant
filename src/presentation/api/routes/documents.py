"""Document management API routes — upload, list, delete."""

import logging
import os
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from src.application.dto.responses import (
    DocumentInfo,
    DocumentListResponse,
    IngestResponse,
    IngestStatusResponse,
)
from src.application.services.ingestion_registry import (
    IngestionStatus,
)
from src.application.services.ingestion_registry import (
    registry as ingestion_registry,
)
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.interfaces.vector_store import VectorStore
from src.infrastructure.config.settings import get_settings
from src.presentation.api.dependencies import Registry

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# Magic bytes per extension. Checking the *content* rather than trusting the
# name is what turns "Ingestion failed." into something the user can act on: a
# renamed executable or a half-downloaded PDF otherwise reaches the parser,
# which raises deep inside PyPDF2, and the route can only report a generic 500.
_MAGIC_BYTES = {
    ".pdf": (b"%PDF",),
    # A DOCX is a ZIP container, so it opens with the local-file-header magic.
    ".docx": (b"PK\x03\x04",),
}


def _looks_like(content: bytes, ext: str) -> bool:
    """Return False when the bytes cannot possibly be the declared type.

    Only checks extensions that have a well-known signature. TXT is excluded on
    purpose: plain text has no magic number, and a UTF-8 BOM or a leading blank
    line would make a naive check reject perfectly good files.
    """
    expected = _MAGIC_BYTES.get(ext)
    if expected is None:
        return True
    return content.startswith(expected)


# Injected at startup by app.py so upload/list/delete share one ChromaStore.
# Two Registries rather than two bare globals: the 503-when-unwired guard is
# then the same code the chat use cases use, instead of a second hand-rolled copy.
_vector_store: Registry[VectorStore] = Registry("Document service")
_embedding_provider: Registry[EmbeddingProvider] = Registry("Embedding service")


def configure(vector_store: VectorStore, embedding_provider: EmbeddingProvider) -> None:
    """Register shared infrastructure dependencies at startup."""
    _vector_store.set(vector_store)
    _embedding_provider.set(embedding_provider)


def _get_dependencies() -> tuple[VectorStore, EmbeddingProvider]:
    """Return the injected dependencies or raise a 503 if not wired."""
    return _vector_store.get(), _embedding_provider.get()


# ---------------------------------------------------------------------------
# POST /documents/upload — upload and ingest a document
# ---------------------------------------------------------------------------


async def _run_ingestion(document_id: str, content: bytes, filename: str) -> None:
    """Parse, embed and store one document.

    Runs after the response has been sent, so every failure here has to be
    reported through the ingestion registry — there is no longer a request to
    raise an HTTPException on.
    """
    ingestion_registry.mark_processing(document_id)
    try:
        settings = get_settings()

        # Lazy import — the use case depends on infra that may not be wired yet.
        from src.application.use_cases.ingest_document import IngestDocumentUseCase
        from src.infrastructure.document_processing.semantic_chunker import (
            SemanticChunker,
        )
        from src.infrastructure.document_processing.text_splitter import TextSplitter

        vector_store, embedding_provider = _get_dependencies()

        if settings.ENABLE_SEMANTIC_CHUNKING:
            text_splitter = SemanticChunker(
                embedding_provider=embedding_provider,
                similarity_threshold=settings.SEMANTIC_SIMILARITY_THRESHOLD,
                min_chunk_size=settings.SEMANTIC_MIN_CHUNK_SIZE,
                max_chunk_size=settings.SEMANTIC_MAX_CHUNK_SIZE,
            )
        else:
            text_splitter = TextSplitter()

        use_case = IngestDocumentUseCase(
            text_splitter=text_splitter,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
        )
        result = await use_case.execute(file_content=content, filename=filename)
        ingestion_registry.mark_complete(document_id, result["chunk_count"])
    except Exception as exc:
        logger.error(
            "Background ingestion failed for '%s': %s", filename, exc, exc_info=True
        )
        ingestion_registry.mark_failed(document_id, f"{type(exc).__name__}: {exc}")


@router.post(
    "/documents/upload",
    response_model=IngestResponse,
    status_code=202,
)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
) -> IngestResponse:
    """Accept a document for ingestion and start processing it in the background.

    Returns `202 Accepted` as soon as the bytes are validated. Ingestion is slow
    by nature — a few hundred pages takes minutes of parsing and embedding — and
    holding the connection open for that long meant the request timed out or the
    browser spun with no feedback, so the work now happens after the response and
    the client polls `GET /documents/status/{document_id}`.

    Validation up front is unchanged and still returns 4xx synchronously: an
    empty file, an unsupported extension, a size over the cap, or content that
    does not match its extension all fail before anything is accepted.
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

    # Reject an oversized upload before reading it. Starlette spools the body to
    # a temp file with no upper bound, and `await file.read()` would pull the
    # whole thing into memory — so an unbounded read here is a trivial way to
    # exhaust RAM (and then the parser gets to decompress it: DOCX is a zip).
    settings = get_settings()
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024

    # Trust the declared length when the client provides one, but do not rely on
    # it: a chunked request can omit Content-Length, so the real guard is the
    # byte counter in the loop below.
    if file.size is not None and file.size > max_bytes:
        await file.close()
        raise HTTPException(
            status_code=413,
            detail=(
                f"File is too large. Maximum size is {settings.MAX_FILE_SIZE_MB} MB."
            ),
        )

    # Read in bounded chunks and abort as soon as the cap is passed, so we never
    # buffer more than the limit regardless of what the client claims.
    buffer = bytearray()
    read_chunk = 1024 * 1024
    while True:
        chunk = await file.read(read_chunk)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            await file.close()
            raise HTTPException(
                status_code=413,
                detail=(
                    f"File is too large. Maximum size is "
                    f"{settings.MAX_FILE_SIZE_MB} MB."
                ),
            )

    content = bytes(buffer)
    await file.close()

    if not content:
        raise HTTPException(status_code=400, detail="Empty file.")

    if not _looks_like(content, ext):
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{file.filename}' does not look like a {ext[1:].upper()} file. "
                "The extension and the contents do not match — the file may be "
                "corrupt, renamed, or a download that did not finish."
            ),
        )

    document_id = str(uuid4())
    ingestion_registry.start(document_id, file.filename)
    background.add_task(_run_ingestion, document_id, content, file.filename)

    return IngestResponse(
        document_id=document_id,
        filename=file.filename,
        chunk_count=0,
        message=(
            f"Accepted '{file.filename}'. Processing has started — it may take "
            "a few minutes for a large document."
        ),
        status=IngestionStatus.PENDING.value,
    )


# ---------------------------------------------------------------------------
# GET /documents/status/{document_id} — background ingestion progress
# ---------------------------------------------------------------------------


@router.get("/documents/status/{document_id}", response_model=IngestStatusResponse)
async def get_ingestion_status(document_id: str) -> IngestStatusResponse:
    """Report how far the background ingestion of one document has got.

    Polled by the upload UI. Returns 404 once the job has aged out of the
    registry, which is not a failure: by then the document has long since
    appeared in `GET /documents`.
    """
    job = ingestion_registry.get(document_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="No ingestion is being tracked for this document.",
        )
    return IngestStatusResponse(**job)


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
        raise HTTPException(status_code=500, detail="Failed to list documents.")

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
# DELETE /documents — delete every document (Danger Zone)
# ---------------------------------------------------------------------------


@router.delete("/documents")
async def delete_all_documents() -> dict:
    """Delete every ingested document and all of its chunks.

    Backs the Danger Zone's "delete all documents" action. Documents are
    removed one at a time by id rather than by dropping the collection, so a
    failure part-way leaves the remaining documents intact instead of silently
    clearing everything. The response reports what was removed and what failed.
    """
    vector_store, _ = _get_dependencies()
    settings = get_settings()

    try:
        docs = await vector_store.list_documents(settings.CHROMA_COLLECTION_NAME)
    except Exception as exc:
        logger.error("Bulk delete: could not list documents: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Could not list documents.")

    deleted: list[str] = []
    failed: list[str] = []
    for doc in docs:
        document_id = doc["document_id"]
        try:
            await vector_store.delete_by_metadata(
                {"document_id": document_id},
                settings.CHROMA_COLLECTION_NAME,
            )
            deleted.append(document_id)
        except Exception:
            # Keep going: one bad document should not strand the rest.
            logger.error(
                "Bulk delete: failed to delete document %s", document_id, exc_info=True
            )
            failed.append(document_id)

    if failed and not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete any documents.")

    return {
        "deleted": len(deleted),
        "failed": len(failed),
        "message": f"Deleted {len(deleted)} document(s).",
    }


# ---------------------------------------------------------------------------
# DELETE /documents/{document_id} — delete a document
# ---------------------------------------------------------------------------


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str) -> dict:
    """Delete a document and all of its chunks from the vector store."""
    vector_store, _ = _get_dependencies()
    settings = get_settings()

    try:
        # Main collection deletion is required — failures propagate as 500.
        await vector_store.delete_by_metadata(
            {"document_id": document_id},
            settings.CHROMA_COLLECTION_NAME,
        )
    except Exception as exc:
        logger.error(
            "Failed to delete document %s: %s", document_id, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to delete document.")

    return {"message": f"Document {document_id} deleted successfully."}
