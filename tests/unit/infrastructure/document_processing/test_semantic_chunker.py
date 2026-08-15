"""Tests for semantic chunking strategy."""

from uuid import uuid4

import numpy as np
import pytest

from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.value_objects.chunk import Chunk


def _make_async_embedder(embed_fn):
    """Build a mock provider matching the real EmbeddingProvider interface.

    ``embed_batch`` is async (like the real Gemini/OpenAI/HuggingFace
    providers), so awaiting it from ``SemanticChunker.split_text`` works.
    """

    class AsyncEmbedder(EmbeddingProvider):
        def __init__(self, fn):
            self._fn = fn

        async def embed(self, text: str) -> list[float]:
            return self._fn(text)

        async def embed_batch(self, texts: list[str]) -> list[list[float]]:
            return [self._fn(t) for t in texts]

        def get_embedding_dimension(self) -> int:
            return len(self._fn("probe"))

    return AsyncEmbedder(embed_fn)


class TestSemanticChunker:
    """Tests for the semantic chunking strategy."""

    @pytest.mark.asyncio
    async def test_semantic_chunker_splits_on_boundary(self):
        """Chunks split where semantic similarity drops."""
        from src.infrastructure.document_processing.semantic_chunker import (
            SemanticChunker,
        )

        # Mock embedding provider: first 3 sentences similar, then a drop
        def mock_embed(text: str) -> list[float]:
            if "cat" in text.lower() or "dog" in text.lower() or "pet" in text.lower():
                return [1.0, 0.0, 0.0]  # pet cluster
            else:
                return [0.0, 0.0, 1.0]  # quantum cluster

        chunker = SemanticChunker(
            embedding_provider=_make_async_embedder(mock_embed),
            similarity_threshold=0.5,
            min_chunk_size=5,
        )
        text = (
            "I love my cat. She is a great pet. My dog is also wonderful. "
            "Quantum computing uses qubits. Entanglement enables parallelism."
        )
        chunks = await chunker.split_text(
            text, uuid4(), metadata={"filename": "test.txt"}
        )

        assert len(chunks) >= 2
        for chunk in chunks:
            assert isinstance(chunk, Chunk)
            assert len(chunk.content) > 0

    @pytest.mark.asyncio
    async def test_semantic_chunker_respects_max_size(self):
        """Chunks never exceed max_chunk_size."""
        from src.infrastructure.document_processing.semantic_chunker import (
            SemanticChunker,
        )

        def constant_embed(text: str) -> list[float]:
            return [1.0, 0.0]

        chunker = SemanticChunker(
            embedding_provider=_make_async_embedder(constant_embed),
            similarity_threshold=0.99,
            min_chunk_size=5,
            max_chunk_size=100,
        )
        # Text with no semantic boundaries — should still split at max size
        text = "This is a test sentence with some words. " * 20
        chunks = await chunker.split_text(text, uuid4())

        for chunk in chunks:
            assert len(chunk.content) <= 150  # allow some slack for word boundaries

    @pytest.mark.asyncio
    async def test_semantic_chunker_handles_single_sentence(self):
        """A single sentence produces a single chunk."""
        from src.infrastructure.document_processing.semantic_chunker import (
            SemanticChunker,
        )

        def mock_embed(text: str) -> list[float]:
            return [1.0]

        chunker = SemanticChunker(
            embedding_provider=_make_async_embedder(mock_embed),
            similarity_threshold=0.5,
            min_chunk_size=5,
        )
        chunks = await chunker.split_text("Hello world.", uuid4())
        assert len(chunks) == 1
        assert "Hello world" in chunks[0].content

    @pytest.mark.asyncio
    async def test_semantic_chunker_empty_text(self):
        """Empty text produces no chunks."""
        from src.infrastructure.document_processing.semantic_chunker import (
            SemanticChunker,
        )

        def mock_embed(text: str) -> list[float]:
            return [0.0]

        chunker = SemanticChunker(
            embedding_provider=_make_async_embedder(mock_embed),
            similarity_threshold=0.5,
            min_chunk_size=5,
        )
        chunks = await chunker.split_text("", uuid4())
        assert chunks == []

    @pytest.mark.asyncio
    async def test_semantic_chunker_preserves_metadata(self):
        """Chunks inherit the provided metadata."""
        from src.infrastructure.document_processing.semantic_chunker import (
            SemanticChunker,
        )

        def mock_embed(text: str) -> list[float]:
            return [1.0]

        chunker = SemanticChunker(
            embedding_provider=_make_async_embedder(mock_embed),
            similarity_threshold=0.5,
            min_chunk_size=5,
        )
        meta = {"filename": "doc.pdf", "source": "test"}
        chunks = await chunker.split_text("Hello. World.", uuid4(), metadata=meta)
        for chunk in chunks:
            assert chunk.metadata["filename"] == "doc.pdf"
            assert chunk.metadata["source"] == "test"

    def test_cosine_similarity_calculation(self):
        """Internal cosine similarity is computed correctly."""
        from src.infrastructure.document_processing.semantic_chunker import (
            _cosine_similarity,
        )

        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        assert _cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)

        c = np.array([1.0, 0.0, 0.0])
        d = np.array([1.0, 0.0, 0.0])
        assert _cosine_similarity(c, d) == pytest.approx(1.0, abs=1e-6)

    def test_sentence_splitting(self):
        """Internal sentence splitting handles common cases."""
        from src.infrastructure.document_processing.semantic_chunker import (
            _split_sentences,
        )

        sents = _split_sentences("Hello world. How are you? I'm fine!")
        assert len(sents) == 3
        assert "Hello" in sents[0]
        assert "How" in sents[1]

    @pytest.mark.asyncio
    async def test_merge_small_segments(self):
        """Small consecutive segments are merged."""
        from src.infrastructure.document_processing.semantic_chunker import (
            SemanticChunker,
        )

        def constant_embed(text: str) -> list[float]:
            return [1.0]

        chunker = SemanticChunker(
            embedding_provider=_make_async_embedder(constant_embed),
            similarity_threshold=0.5,
            min_chunk_size=50,
            max_chunk_size=500,
        )
        # Many short sentences — should merge into fewer chunks
        text = " ".join(f"Word{i}." for i in range(50))
        chunks = await chunker.split_text(text, uuid4())
        assert len(chunks) < 50  # definitely merged

    @pytest.mark.asyncio
    async def test_split_text_awaits_async_embed_batch(self):
        """Proves split_text awaits the async embed_batch (C1 regression).

        The provider below follows the real ``EmbeddingProvider`` contract
        (async ``embed_batch``). Before the C1 fix, ``split_text`` called
        ``embed_batch`` without awaiting, which returned an un-awaited
        coroutine and crashed with ``TypeError``.
        """
        from unittest.mock import AsyncMock

        from src.infrastructure.document_processing.semantic_chunker import (
            SemanticChunker,
        )

        provider = AsyncMock()
        provider.embed_batch = AsyncMock(
            return_value=[[1.0, 0.0], [1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
        )

        chunker = SemanticChunker(
            embedding_provider=provider,
            similarity_threshold=0.5,
            min_chunk_size=5,
        )
        text = (
            "Cats are pets. Dogs are pets. Birds are pets. "
            "Quantum computing is a different topic."
        )
        chunks = await chunker.split_text(text, uuid4())

        provider.embed_batch.assert_awaited()
        assert len(chunks) >= 2
        for chunk in chunks:
            assert isinstance(chunk, Chunk)
