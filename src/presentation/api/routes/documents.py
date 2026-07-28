"""Document management API routes — upload, list, delete."""

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from src.application.dto.responses import (
    IngestResponse,
    DocumentListResponse,
    DocumentInfo,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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

    allowed = {".pdf", ".docx", ".txt"}
    import os
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(allowed)}",
        )

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file.")

        # Lazy import — use case depends on infra that may not be wired yet
        from src.infrastructure.config.settings import get_settings
        from src.infrastructure.document_processing.text_splitter import TextSplitter
        from src.infrastructure.embeddings.factory import EmbeddingProviderFactory
        from src.infrastructure.vector_store.chroma_store import ChromaStore
        from src.application.use_cases.ingest_document import IngestDocumentUseCase
        from src.infrastructure.document_processing.parser_factory import create_parser

        settings = get_settings()
        parser = create_parser(ext)
        splitter = TextSplitter()
        embedding_provider = EmbeddingProviderFactory.create(settings)
        vector_store = ChromaStore(persist_directory=settings.CHROMA_PERSIST_DIR)

        use_case = IngestDocumentUseCase(
            parser=parser,
            text_splitter=splitter,
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
    """Return a list of all ingested documents.

    Note: Currently returns a placeholder until a document listing
    use case backed by persistent metadata is implemented.
    """
    return DocumentListResponse(documents=[], total=0)


# ---------------------------------------------------------------------------
# DELETE /documents/{document_id} — delete a document
# ---------------------------------------------------------------------------


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str) -> dict:
    """Delete a document and its chunks from the vector store.

    Note: Currently a placeholder.
    """
    return {"message": f"Document {document_id} deletion not yet implemented."}
