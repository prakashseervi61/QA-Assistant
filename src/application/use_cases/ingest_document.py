"""Use case for ingesting documents into the vector store.

Orchestrates the full ingestion pipeline:
  file bytes → parse → split → embed → store
"""

import hashlib
import io
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.interfaces.vector_store import VectorStore
from src.domain.value_objects.chunk import Chunk
from src.infrastructure.config.settings import get_settings
from src.infrastructure.document_processing.parser_factory import create_parser
from src.infrastructure.document_processing.semantic_chunker import SemanticChunker
from src.infrastructure.document_processing.text_splitter import TextSplitter

logger = logging.getLogger(__name__)


def compute_content_hash(file_bytes: bytes) -> str:
    """Compute a stable SHA-256 hex digest of raw file bytes.

    Used by incremental ingestion to detect re-uploads of byte-identical
    files. The digest is stored in every chunk's metadata and compared
    on subsequent uploads (see ``ENABLE_INCREMENTAL_INGESTION``).
    """
    return hashlib.sha256(file_bytes).hexdigest()


class DocumentIngestionError(Exception):
    """Raised when document ingestion fails."""


class IngestDocumentUseCase:
    """Orchestrates document ingestion: parse → split → embed → store."""

    def __init__(
        self,
        text_splitter: TextSplitter | SemanticChunker,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        # No parser injection: execute() builds the right parser from the file
        # extension via create_parser(), so a ctor-supplied one was never read.
        self._text_splitter = text_splitter
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    async def _find_duplicate(
        self, content_hash: str, collection_name: str
    ) -> tuple[Chunk, int] | None:
        """Find existing chunks whose metadata carries *content_hash*.

        A missing collection yields no matches (``get_by_metadata``
        returns an empty list for it). Chunks ingested before
        ``document_id`` became part of the metadata (legacy documents)
        come back with a None document_id; skip them so a duplicate
        result can never surface a bogus "None" document id.

        Returns:
            ``(first matching chunk, total number of matching chunks)``,
            or ``None`` when no chunk with the hash exists yet.
        """
        matches = await self._vector_store.get_by_metadata(
            {"content_hash": content_hash}, collection_name
        )
        valid_matches = [match for match in matches if match.document_id is not None]
        if not valid_matches:
            return None
        return valid_matches[0], len(valid_matches)

    async def execute(self, file_content: bytes, filename: str) -> dict:
        """Execute the document ingestion pipeline.

        Steps:
            1. Generate a unique document ID.
            2. Validate the file extension against supported types.
            3. (Feature-gated) Detect byte-identical re-uploads via
               SHA-256 content hash and return a duplicate result
               without parsing/embedding/storing.
            4. Parse the raw bytes into plain text.
            5. Split the text into overlapping chunks.
            6. Generate embedding vectors for every chunk.
            7. Persist chunks + embeddings in the vector store.

        Args:
            file_content: Raw bytes of the uploaded file.
            filename: Name of the uploaded file (used to infer the
                      correct parser via its extension).

        Returns:
            dict with keys:
                - document_id  (str)  – unique identifier for the document
                - filename     (str)  – original filename
                - chunk_count  (int)  – number of chunks created
                - collection   (str)  – vector store collection used
                - message      (str)  – human-readable summary

            When ``ENABLE_INCREMENTAL_INGESTION`` is on and the content
            hash already exists, additionally includes:
                - status   (str)  – ``"duplicate"``
                - duplicate (bool) – ``True``

        Raises:
            DocumentIngestionError: On any failure during the pipeline.
        """
        settings = get_settings()
        collection_name = settings.CHROMA_COLLECTION_NAME

        document_id = uuid4()
        logger.info(
            "Starting ingestion for '%s' (document_id=%s)", filename, document_id
        )

        try:
            extension = Path(filename).suffix.lower()
            if not extension:
                raise DocumentIngestionError(
                    f"Cannot determine file type from filename '{filename}'. "
                    "File must have an extension (e.g. .pdf, .docx, .txt)."
                )

            # --- Incremental ingestion (feature-gated, OFF by default) ---
            # When enabled, a byte-identical file whose SHA-256 content
            # hash already exists in the vector store is reported as a
            # duplicate WITHOUT parsing, embedding, or storing. When
            # disabled, no hash is computed or stored (zero overhead,
            # behavior unchanged).
            content_hash: str | None = None
            if getattr(settings, "ENABLE_INCREMENTAL_INGESTION", False):
                content_hash = compute_content_hash(file_content)
                duplicate = await self._find_duplicate(content_hash, collection_name)
                if duplicate is not None:
                    chunk, chunk_count = duplicate
                    logger.info(
                        "Duplicate detected for '%s' (content_hash=%s)",
                        filename,
                        content_hash,
                    )
                    return {
                        "document_id": str(chunk.document_id),
                        "filename": filename,
                        "chunk_count": chunk_count,
                        "collection": collection_name,
                        "status": "duplicate",
                        "message": (
                            f"Document '{filename}' already ingested "
                            "(duplicate detected)."
                        ),
                        "duplicate": True,
                    }

            parser = create_parser(extension)

            file_stream = io.BytesIO(file_content)
            parsed_text = await parser.parse(file_stream)

            if not parsed_text or not parsed_text.strip():
                raise DocumentIngestionError(
                    f"Document '{filename}' produced no extractable text."
                )

            logger.info(
                "Parsed '%s': %d characters extracted", filename, len(parsed_text)
            )

            metadata = {
                "filename": filename,
                "file_type": extension,
                "file_size": len(file_content),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            if content_hash is not None:
                metadata["content_hash"] = content_hash

            # Split the parsed text into chunks before embedding.
            chunks = await self._text_splitter.split_text(
                text=parsed_text,
                document_id=document_id,
                metadata=metadata,
            )
            logger.info("Split into %d chunks", len(chunks))

            chunk_texts = [chunk.content for chunk in chunks]
            embeddings = await self._embedding_provider.embed_batch(chunk_texts)

            if len(embeddings) != len(chunks):
                raise DocumentIngestionError(
                    f"Embedding count mismatch: expected {len(chunks)} embeddings "
                    f"but received {len(embeddings)}."
                )

            embedded_chunks: list[Chunk] = []
            for chunk, embedding in zip(chunks, embeddings):
                embedded_chunk = Chunk(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    content=chunk.content,
                    embedding=embedding,
                    metadata=chunk.metadata,
                    chunk_index=chunk.chunk_index,
                )
                embedded_chunks.append(embedded_chunk)

            logger.info(
                "Generated %d embeddings (dim=%d) for '%s'",
                len(embedded_chunks),
                self._embedding_provider.get_embedding_dimension(),
                filename,
            )

            await self._vector_store.add_documents(embedded_chunks, collection_name)

            logger.info(
                "Stored %d chunks in collection '%s' for document %s",
                len(embedded_chunks),
                collection_name,
                document_id,
            )

            total_chunks = len(embedded_chunks)

            return {
                "document_id": str(document_id),
                "filename": filename,
                "chunk_count": total_chunks,
                "collection": collection_name,
                "message": (
                    f"Successfully ingested '{filename}'. {total_chunks} chunks stored."
                ),
            }

        except DocumentIngestionError:
            # Re-raise our own errors unchanged
            raise
        except Exception as exc:
            logger.error("Ingestion failed for '%s': %s", filename, exc, exc_info=True)
            raise DocumentIngestionError(
                f"Failed to ingest document '{filename}': {exc}"
            ) from exc
