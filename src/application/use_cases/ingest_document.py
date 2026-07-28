"""Use case for ingesting documents into the vector store.

Orchestrates the full ingestion pipeline:
  file bytes → parse → split → embed → store
"""

import io
import logging
from pathlib import Path
from uuid import uuid4

from src.domain.interfaces.document_parser import DocumentParser
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.interfaces.vector_store import VectorStore
from src.domain.value_objects.chunk import Chunk
from src.infrastructure.config.settings import get_settings
from src.infrastructure.document_processing.parser_factory import create_parser
from src.infrastructure.document_processing.text_splitter import TextSplitter

logger = logging.getLogger(__name__)


class DocumentIngestionError(Exception):
    """Raised when document ingestion fails."""


class IngestDocumentUseCase:
    """Orchestrates document ingestion: parse → split → embed → store."""

    def __init__(
        self,
        parser: DocumentParser,
        text_splitter: TextSplitter,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        self._parser = parser
        self._text_splitter = text_splitter
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    async def execute(self, file_content: bytes, filename: str) -> dict:
        """Execute the document ingestion pipeline.

        Steps:
            1. Generate a unique document ID.
            2. Validate the file extension against supported types.
            3. Parse the raw bytes into plain text.
            4. Split the text into overlapping chunks.
            5. Generate embedding vectors for every chunk.
            6. Persist chunks + embeddings in the vector store.

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

        Raises:
            DocumentIngestionError: On any failure during the pipeline.
        """
        settings = get_settings()
        collection_name = settings.CHROMA_COLLECTION_NAME

        document_id = uuid4()
        logger.info("Starting ingestion for '%s' (document_id=%s)", filename, document_id)

        try:
            extension = Path(filename).suffix.lower()
            if not extension:
                raise DocumentIngestionError(
                    f"Cannot determine file type from filename '{filename}'. "
                    "File must have an extension (e.g. .pdf, .docx, .txt)."
                )

            parser = create_parser(extension)

            file_stream = io.BytesIO(file_content)
            parsed_text = await parser.parse(file_stream)

            if not parsed_text or not parsed_text.strip():
                raise DocumentIngestionError(
                    f"Document '{filename}' produced no extractable text."
                )

            logger.info("Parsed '%s': %d characters extracted", filename, len(parsed_text))

            metadata = {
                "filename": filename,
                "file_type": extension,
                "file_size": len(file_content),
            }

            chunks = self._text_splitter.split_text(
                text=parsed_text,
                document_id=document_id,
                metadata=metadata,
            )

            if not chunks:
                raise DocumentIngestionError(
                    f"Text splitting produced zero chunks for '{filename}'."
                )

            logger.info(
                "Split '%s' into %d chunks (chunk_size=%d, overlap=%d)",
                filename, len(chunks), self._text_splitter.chunk_size, self._text_splitter.chunk_overlap,
            )

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
                    id=chunk.id, document_id=chunk.document_id, content=chunk.content,
                    embedding=embedding, metadata=chunk.metadata, chunk_index=chunk.chunk_index,
                )
                embedded_chunks.append(embedded_chunk)

            logger.info(
                "Generated %d embeddings (dim=%d) for '%s'",
                len(embedded_chunks), self._embedding_provider.get_embedding_dimension(), filename,
            )

            await self._vector_store.add_documents(embedded_chunks, collection_name)

            logger.info(
                "Stored %d chunks in collection '%s' for document %s",
                len(embedded_chunks), collection_name, document_id,
            )

            return {
                "document_id": str(document_id),
                "filename": filename,
                "chunk_count": len(embedded_chunks),
                "collection": collection_name,
                "message": f"Successfully ingested '{filename}'. {len(embedded_chunks)} chunks stored.",
            }

        except DocumentIngestionError:
            # Re-raise our own errors unchanged
            raise
        except Exception as exc:
            logger.error("Ingestion failed for '%s': %s", filename, exc, exc_info=True)
            raise DocumentIngestionError(
                f"Failed to ingest document '{filename}': {exc}"
            ) from exc
