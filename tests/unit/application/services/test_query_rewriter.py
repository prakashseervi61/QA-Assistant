"""Tests for QueryRewriter interface, service, and RRF fusion."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.value_objects.chunk import Chunk

# --- QueryRewriter ABC ---


class TestQueryRewriterInterface:
    def test_query_rewriter_is_abstract(self):
        from src.domain.interfaces.query_rewriter import QueryRewriter

        with pytest.raises(TypeError):
            QueryRewriter()

    def test_query_rewriter_has_rewrite_method(self):
        from src.domain.interfaces.query_rewriter import QueryRewriter

        assert hasattr(QueryRewriter, "rewrite")

    def test_concrete_subclass_works(self):
        from src.domain.interfaces.query_rewriter import QueryRewriter

        class Dummy(QueryRewriter):
            async def rewrite(self, query: str, num_queries: int = 3) -> list[str]:
                return [query]

            async def hyde_embed(self, query: str) -> list[float]:
                return [0.1]

        r = Dummy()
        assert r is not None


# --- QueryRewriterService ---


@pytest.mark.asyncio
class TestQueryRewriterService:
    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        llm.generate = AsyncMock(
            return_value="What is ML?\nDefine machine learning\nML explanation"
        )
        return llm

    @pytest.fixture
    def mock_embedding(self):
        emb = AsyncMock()
        emb.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
        return emb

    @pytest.fixture
    def mock_vector_store(self):
        store = AsyncMock()
        store.similarity_search = AsyncMock(return_value=[])
        store.hybrid_search = AsyncMock(return_value=[])
        return store

    async def test_rewrite_returns_list_of_strings(
        self, mock_llm, mock_embedding, mock_vector_store
    ):
        from src.application.services.query_rewriter import QueryRewriterService

        rw = QueryRewriterService(mock_llm, mock_embedding, mock_vector_store)
        result = await rw.rewrite("What is AI?", num_queries=3)
        assert isinstance(result, list)
        assert all(isinstance(q, str) for q in result)

    async def test_rewrite_includes_original_query(
        self, mock_llm, mock_embedding, mock_vector_store
    ):
        from src.application.services.query_rewriter import QueryRewriterService

        rw = QueryRewriterService(mock_llm, mock_embedding, mock_vector_store)
        result = await rw.rewrite("What is AI?", num_queries=3)
        assert "What is AI?" in result

    async def test_rewrite_calls_llm_generate(
        self, mock_llm, mock_embedding, mock_vector_store
    ):
        from src.application.services.query_rewriter import QueryRewriterService

        rw = QueryRewriterService(mock_llm, mock_embedding, mock_vector_store)
        await rw.rewrite("test query", num_queries=2)
        mock_llm.generate.assert_awaited_once()

    async def test_rewrite_strips_empty_lines(
        self, mock_llm, mock_embedding, mock_vector_store
    ):
        from src.application.services.query_rewriter import QueryRewriterService

        mock_llm.generate = AsyncMock(return_value="q1\n\n\nq2\n\n")
        rw = QueryRewriterService(mock_llm, mock_embedding, mock_vector_store)
        result = await rw.rewrite("test", num_queries=3)
        assert "" not in result

    async def test_rewrite_clamps_num_queries_zero(
        self, mock_llm, mock_embedding, mock_vector_store
    ):
        """num_queries=0 is clamped to 1 — original query only (N3)."""
        from src.application.services.query_rewriter import QueryRewriterService

        mock_llm.generate = AsyncMock(return_value="variant1\nvariant2")
        rw = QueryRewriterService(mock_llm, mock_embedding, mock_vector_store)
        result = await rw.rewrite("original query", num_queries=0)
        assert result == ["original query"]

    async def test_rewrite_num_queries_one_returns_original_only(
        self, mock_llm, mock_embedding, mock_vector_store
    ):
        """num_queries=1 returns just the original query."""
        from src.application.services.query_rewriter import QueryRewriterService

        mock_llm.generate = AsyncMock(return_value="variant1\nvariant2")
        rw = QueryRewriterService(mock_llm, mock_embedding, mock_vector_store)
        result = await rw.rewrite("original query", num_queries=1)
        assert result == ["original query"]

    async def test_hyde_embed_returns_embedding(
        self, mock_llm, mock_embedding, mock_vector_store
    ):
        from src.application.services.query_rewriter import QueryRewriterService

        rw = QueryRewriterService(mock_llm, mock_embedding, mock_vector_store)
        emb = await rw.hyde_embed("What is ML?")
        assert isinstance(emb, list)
        mock_llm.generate.assert_awaited_once()
        mock_embedding.embed.assert_awaited_once()


# --- RRF Fusion ---


class TestRRFFusion:
    def _make_chunks(self, ids):
        return [
            Chunk(
                content=f"chunk {cid}",
                metadata={"score": 0.9 - i * 0.1},
                chunk_index=i,
            )
            for i, cid in enumerate(ids)
        ]

    def test_rrf_fuse_basic(self):
        from src.application.services.rag_engine import RAGEngine

        list_a = self._make_chunks(["a", "b", "c"])
        list_b = self._make_chunks(["b", "c", "d"])

        result = RAGEngine._rrf_fuse([list_a, list_b], k=5)

        assert len(result) <= 5
        contents = [c.content for c in result]
        # "b" and "c" appear in both lists so should rank higher
        assert "chunk b" in contents
        assert "chunk c" in contents

    def test_rrf_fuse_empty_lists(self):
        from src.application.services.rag_engine import RAGEngine

        result = RAGEngine._rrf_fuse([], k=5)
        assert result == []

    def test_rrf_fuse_single_list(self):
        from src.application.services.rag_engine import RAGEngine

        chunks = self._make_chunks(["x", "y"])
        result = RAGEngine._rrf_fuse([chunks], k=2)
        assert len(result) == 2

    def test_rrf_fuse_respects_k(self):
        from src.application.services.rag_engine import RAGEngine

        chunks = self._make_chunks(["a", "b", "c", "d", "e"])
        result = RAGEngine._rrf_fuse([chunks], k=2)
        assert len(result) == 2

    def test_rrf_fuse_deduplicates_chunks(self):
        from src.application.services.rag_engine import RAGEngine

        chunk = Chunk(content="same", metadata={}, chunk_index=0)
        result = RAGEngine._rrf_fuse([[chunk], [chunk]], k=5)
        assert len(result) == 1

    def test_rrf_fuse_keeps_max_score_occurrence(self):
        """When the same chunk id appears multiple times, the occurrence
        with the highest similarity score wins (N4)."""
        from uuid import uuid4

        from src.application.services.rag_engine import RAGEngine

        shared_id = uuid4()
        low = Chunk(
            id=shared_id,
            content="low score copy",
            metadata={"score": 0.4},
            chunk_index=0,
        )
        high = Chunk(
            id=shared_id,
            content="high score copy",
            metadata={"score": 0.9},
            chunk_index=0,
        )
        result = RAGEngine._rrf_fuse([[low], [high]], k=5)
        assert len(result) == 1
        assert result[0].content == "high score copy"

    def test_rrf_fuse_ignores_non_numeric_scores(self):
        """Non-numeric scores fall back to 0.0 without crashing."""
        from uuid import uuid4

        from src.application.services.rag_engine import RAGEngine

        shared_id = uuid4()
        bad = Chunk(
            id=shared_id,
            content="bad score",
            metadata={"score": "n/a"},
            chunk_index=0,
        )
        good = Chunk(
            id=shared_id,
            content="good score",
            metadata={"score": 0.8},
            chunk_index=0,
        )
        result = RAGEngine._rrf_fuse([[bad], [good]], k=5)
        assert len(result) == 1
        assert result[0].content == "good score"


# --- Factory ---


class TestQueryRewriterFactory:
    @patch("src.infrastructure.llm.query_rewriter_factory.get_settings")
    def test_factory_returns_none_when_disabled(self, mock_get_settings):
        from src.infrastructure.llm.query_rewriter_factory import (
            create_query_rewriter,
        )

        mock_settings = MagicMock()
        mock_settings.ENABLE_QUERY_REWRITING = False
        mock_get_settings.return_value = mock_settings
        result = create_query_rewriter(AsyncMock(), AsyncMock(), AsyncMock())
        assert result is None

    @patch("src.application.services.query_rewriter.QueryRewriterService")
    @patch("src.infrastructure.llm.query_rewriter_factory.get_settings")
    def test_factory_returns_service_when_enabled(
        self, mock_get_settings, mock_svc_cls
    ):
        from src.infrastructure.llm.query_rewriter_factory import (
            create_query_rewriter,
        )

        mock_settings = MagicMock()
        mock_settings.ENABLE_QUERY_REWRITING = True
        mock_get_settings.return_value = mock_settings
        llm, emb, vs = AsyncMock(), AsyncMock(), AsyncMock()
        result = create_query_rewriter(llm, emb, vs)
        mock_svc_cls.assert_called_once_with(llm, emb, vs)
        assert result is mock_svc_cls.return_value
