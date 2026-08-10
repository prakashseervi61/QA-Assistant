"""Tests for ChromaStore.get_by_metadata (incremental ingestion lookup)."""

from uuid import uuid4

import pytest

from src.domain.value_objects.chunk import Chunk
from src.infrastructure.vector_store.chroma_store import ChromaStore


class TestChromaStoreGetByMetadata:
    """get_by_metadata() must find chunks by metadata filter."""

    @pytest.fixture
    def store(self, tmp_path):
        return ChromaStore(str(tmp_path))

    @pytest.mark.asyncio
    async def test_returns_matching_chunks(self, store):
        """Chunks whose metadata matches the filter are returned."""
        document_id = uuid4()
        chunks = [
            Chunk(
                content="first",
                embedding=[0.1, 0.2, 0.3],
                metadata={"content_hash": "abc123", "filename": "a.txt"},
                chunk_index=0,
            ),
            Chunk(
                content="second",
                embedding=[0.4, 0.5, 0.6],
                metadata={"content_hash": "def456", "filename": "b.txt"},
                chunk_index=0,
            ),
        ]
        # Explicit document_id so the duplicate path can report it.
        for chunk in chunks:
            chunk.metadata["document_id"] = str(document_id)

        await store.add_documents(chunks, "documents")

        results = await store.get_by_metadata(
            {"content_hash": "abc123"}, "documents"
        )

        assert len(results) == 1
        assert results[0].content == "first"
        assert results[0].metadata["content_hash"] == "abc123"
        assert results[0].document_id == document_id

    @pytest.mark.asyncio
    async def test_no_match_returns_empty(self, store):
        """No chunks with the hash -> empty list."""
        await store.add_documents(
            [
                Chunk(
                    content="first",
                    embedding=[0.1, 0.2, 0.3],
                    metadata={"content_hash": "abc123"},
                    chunk_index=0,
                )
            ],
            "documents",
        )

        results = await store.get_by_metadata(
            {"content_hash": "nope"}, "documents"
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_missing_collection_returns_empty(self, store):
        """A collection that does not exist yields no matches."""
        results = await store.get_by_metadata(
            {"content_hash": "abc123"}, "documents"
        )
        assert results == []
