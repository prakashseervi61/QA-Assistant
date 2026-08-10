"""Tests for incremental (hash-based) ingestion.

Locks in the three behaviors of the feature gate:
  (a) ENABLE_INCREMENTAL_INGESTION=True + existing content hash
      -> duplicate early return with NO parsing/embedding/storage,
  (b) ENABLE_INCREMENTAL_INGESTION=True + no existing hash
      -> normal ingest with ``content_hash`` stored in chunk metadata,
  (c) ENABLE_INCREMENTAL_INGESTION=False
      -> 100% previous behavior: normal ingest, no hash lookups.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domain.value_objects.chunk import Chunk


class TestContentHash:
    """compute_content_hash() must be stable and content-sensitive."""

    def test_hash_is_stable(self):
        """Same bytes -> same hash."""
        from src.application.use_cases.ingest_document import compute_content_hash

        h1 = compute_content_hash(b"hello world")
        h2 = compute_content_hash(b"hello world")
        assert h1 == h2
        assert len(h1) == 64  # sha256 hex

    def test_hash_differs_for_different_content(self):
        """Different bytes -> different hash."""
        from src.application.use_cases.ingest_document import compute_content_hash

        assert compute_content_hash(b"hello") != compute_content_hash(b"world")


class TestIncrementalIngest:
    """Duplicate detection during ingestion."""

    @pytest.fixture
    def deps(self):
        """Mocked ingestion dependencies, mirroring the real wire-up."""
        from src.infrastructure.document_processing.text_splitter import TextSplitter

        parser = AsyncMock()
        parser.parse.return_value = "Hello world. " * 50

        embedding_provider = AsyncMock()

        async def dynamic_embed_batch(texts):
            return [[0.1] * 4 for _ in texts]

        embedding_provider.embed_batch = AsyncMock(side_effect=dynamic_embed_batch)
        embedding_provider.get_embedding_dimension = MagicMock(return_value=4)

        vector_store = AsyncMock()
        splitter = TextSplitter(chunk_size=100, chunk_overlap=10)
        return {
            "parser": parser,
            "embedding_provider": embedding_provider,
            "vector_store": vector_store,
            "splitter": splitter,
        }

    @pytest.fixture
    def use_case(self, deps):
        """Build IngestDocumentUseCase with mocked deps."""
        from src.application.use_cases.ingest_document import (
            IngestDocumentUseCase,
        )

        return IngestDocumentUseCase(
            parser=deps["parser"],
            text_splitter=deps["splitter"],
            embedding_provider=deps["embedding_provider"],
            vector_store=deps["vector_store"],
        )

    @pytest.fixture
    def ingest_ctx(self, deps):
        """Context manager patching get_settings + create_parser."""

        @contextmanager
        def _ctx(**overrides):
            settings = MagicMock()
            settings.CHROMA_COLLECTION_NAME = "documents"
            settings.ENABLE_PARENT_CHILD = False
            settings.ENABLE_CHUNK_ENRICHMENT = False
            settings.ENABLE_INCREMENTAL_INGESTION = False
            for key, value in overrides.items():
                setattr(settings, key, value)
            with (
                patch(
                    "src.application.use_cases.ingest_document.get_settings",
                    return_value=settings,
                ),
                patch(
                    "src.application.use_cases.ingest_document.create_parser",
                    return_value=deps["parser"],
                ),
            ):
                yield settings

        return _ctx

    @pytest.mark.asyncio
    async def test_duplicate_detected_when_enabled(self, use_case, deps, ingest_ctx):
        """Enabled + existing hash -> duplicate result, no store/parse/embed."""
        from src.application.use_cases.ingest_document import compute_content_hash

        existing_document_id = uuid4()
        existing_chunks = [
            Chunk(
                id=uuid4(),
                document_id=existing_document_id,
                content="chunk one",
                metadata={"filename": "doc.pdf"},
                chunk_index=0,
            ),
            Chunk(
                id=uuid4(),
                document_id=existing_document_id,
                content="chunk two",
                metadata={"filename": "doc.pdf"},
                chunk_index=1,
            ),
        ]

        def _lookup(metadata_filter, collection_name):
            # Only the main collection holds the duplicate; parent/child
            # collections are empty.
            return existing_chunks if collection_name == "documents" else []

        deps["vector_store"].get_by_metadata = AsyncMock(side_effect=_lookup)

        with ingest_ctx(ENABLE_INCREMENTAL_INGESTION=True):
            result = await use_case.execute(b"same content", "doc.pdf")

        assert result.get("duplicate") is True
        assert result["status"] == "duplicate"
        assert result["document_id"] == str(existing_document_id)
        assert result["filename"] == "doc.pdf"
        assert result["chunk_count"] == 2
        assert "duplicate" in result["message"].lower()

        # The lookup must be by the content hash of the uploaded bytes.
        lookup_filters = [
            call.args[0] for call in deps["vector_store"].get_by_metadata.call_args_list
        ]
        assert lookup_filters[0] == {
            "content_hash": compute_content_hash(b"same content")
        }

        # No parsing, no embedding, no storage.
        deps["vector_store"].add_documents.assert_not_called()
        deps["parser"].parse.assert_not_called()
        deps["embedding_provider"].embed_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_detected_in_parent_child_collections(
        self, use_case, deps, ingest_ctx
    ):
        """Enabled + hash found only in the _parent collection -> duplicate."""
        existing_document_id = uuid4()
        existing = Chunk(
            id=uuid4(),
            document_id=existing_document_id,
            content="parent chunk",
            metadata={"filename": "doc.pdf", "chunk_type": "parent"},
            chunk_index=0,
        )

        def _lookup(metadata_filter, collection_name):
            return [existing] if collection_name == "documents_parent" else []

        deps["vector_store"].get_by_metadata = AsyncMock(side_effect=_lookup)

        with ingest_ctx(ENABLE_INCREMENTAL_INGESTION=True):
            result = await use_case.execute(b"same content", "doc.pdf")

        assert result.get("duplicate") is True
        assert result["document_id"] == str(existing_document_id)
        deps["vector_store"].add_documents.assert_not_called()
        deps["parser"].parse.assert_not_called()

    @pytest.mark.asyncio
    async def test_normal_ingest_stores_hash_when_enabled(
        self, use_case, deps, ingest_ctx
    ):
        """Enabled + no existing hash -> normal ingest with hash stored."""
        from src.application.use_cases.ingest_document import compute_content_hash

        deps["vector_store"].get_by_metadata = AsyncMock(return_value=[])

        with ingest_ctx(ENABLE_INCREMENTAL_INGESTION=True):
            result = await use_case.execute(b"new content", "doc.pdf")

        assert result.get("duplicate", False) is False
        assert result["chunk_count"] > 0

        # Normal pipeline ran to completion.
        deps["vector_store"].add_documents.assert_called_once()
        deps["parser"].parse.assert_called_once()

        # Every stored chunk carries the content hash in its metadata so
        # the duplicate check can find it on later uploads.
        stored_chunks = deps["vector_store"].add_documents.call_args[0][0]
        expected_hash = compute_content_hash(b"new content")
        assert stored_chunks
        for chunk in stored_chunks:
            assert chunk.metadata.get("content_hash") == expected_hash

        # The duplicate lookup did happen (and found nothing).
        assert deps["vector_store"].get_by_metadata.call_count >= 1

    @pytest.mark.asyncio
    async def test_legacy_chunk_without_document_id_not_duplicate(
        self, use_case, deps, ingest_ctx
    ):
        """get_by_metadata chunks lacking document_id are skipped.

        Legacy documents (ingested before document_id was stored in
        metadata) come back with a None document_id; they must never
        trigger the duplicate path with a bogus "None" id.
        """
        legacy_chunks = [
            Chunk(
                id=uuid4(),
                document_id=None,
                content="legacy chunk",
                metadata={"filename": "legacy.pdf", "content_hash": "x"},
                chunk_index=0,
            ),
            Chunk(
                id=uuid4(),
                document_id=None,
                content="legacy chunk two",
                metadata={"filename": "legacy.pdf", "content_hash": "x"},
                chunk_index=1,
            ),
        ]

        def _lookup(metadata_filter, collection_name):
            return legacy_chunks if collection_name == "documents" else []

        deps["vector_store"].get_by_metadata = AsyncMock(side_effect=_lookup)

        with ingest_ctx(ENABLE_INCREMENTAL_INGESTION=True):
            result = await use_case.execute(b"same content", "doc.pdf")

        # No duplicate path: the normal ingest pipeline ran to completion.
        assert result.get("duplicate", False) is False
        assert result["chunk_count"] > 0
        deps["vector_store"].add_documents.assert_called_once()
        deps["parser"].parse.assert_called_once()
        assert "None" not in str(result.get("document_id"))

    @pytest.mark.asyncio
    async def test_behavior_unchanged_when_disabled(self, use_case, deps, ingest_ctx):
        """Disabled -> normal ingest, no hash lookups, no hash stored."""
        with ingest_ctx(ENABLE_INCREMENTAL_INGESTION=False):
            result = await use_case.execute(b"whatever", "doc.pdf")

        assert result.get("duplicate", False) is False
        assert result["chunk_count"] > 0
        deps["vector_store"].add_documents.assert_called_once()

        # Zero overhead: no duplicate lookup, no hash stored.
        deps["vector_store"].get_by_metadata.assert_not_called()
        stored_chunks = deps["vector_store"].add_documents.call_args[0][0]
        for chunk in stored_chunks:
            assert "content_hash" not in chunk.metadata
