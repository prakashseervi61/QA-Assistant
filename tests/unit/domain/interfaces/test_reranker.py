"""Tests for the Reranker interface and BGE implementation."""

from unittest.mock import MagicMock, patch

import pytest

from src.domain.interfaces.reranker import Reranker
from src.domain.value_objects.chunk import Chunk


class TestRerankerInterface:
    """Tests that Reranker is a proper abstract interface."""

    def test_reranker_is_abstract(self):
        """Cannot instantiate Reranker directly."""
        with pytest.raises(TypeError):
            Reranker()

    def test_reranker_has_rerank_method(self):
        """Reranker must define rerank method."""
        assert hasattr(Reranker, "rerank")

    def test_concrete_implementation_works(self):
        """A concrete subclass can be instantiated."""

        class DummyReranker(Reranker):
            def rerank(self, query, chunks, top_k=5):
                return chunks[:top_k]

        r = DummyReranker()
        assert r is not None


class TestBEReranker:
    """Tests for the BGE reranker implementation."""

    @pytest.fixture
    def sample_chunks(self):
        return [
            Chunk(
                content="Machine learning",
                metadata={"filename": "ai.pdf", "page": 1, "score": 0.9},
                chunk_index=0,
            ),
            Chunk(
                content="Deep learning",
                metadata={"filename": "dl.pdf", "page": 2, "score": 0.8},
                chunk_index=1,
            ),
            Chunk(
                content="NLP basics",
                metadata={"filename": "nlp.pdf", "page": 3, "score": 0.7},
                chunk_index=2,
            ),
        ]

    @patch("src.infrastructure.rerankers.bge_reranker.CrossEncoder")
    def test_rerank_returns_reranker_base_type(self, mock_cross_encoder_cls):
        """Reranker must return a Reranker subclass."""
        from src.infrastructure.rerankers.bge_reranker import BEReranker

        mock_model = MagicMock()
        mock_cross_encoder_cls.return_value = mock_model

        r = BEReranker(model_name="test-model")
        assert isinstance(r, Reranker)

    @patch("src.infrastructure.rerankers.bge_reranker.CrossEncoder")
    def test_rerank_returns_correct_number_of_chunks(
        self, mock_cross_encoder_cls, sample_chunks
    ):
        """Reranker returns top_k chunks."""
        from src.infrastructure.rerankers.bge_reranker import BEReranker

        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9, 0.5, 0.3]
        mock_cross_encoder_cls.return_value = mock_model

        r = BEReranker(model_name="test-model")
        result = r.rerank("What is AI?", sample_chunks, top_k=2)

        assert len(result) == 2

    @patch("src.infrastructure.rerankers.bge_reranker.CrossEncoder")
    def test_rerank_adds_rerank_score_to_metadata(
        self, mock_cross_encoder_cls, sample_chunks
    ):
        """Reranker adds rerank_score to chunk metadata."""
        from src.infrastructure.rerankers.bge_reranker import BEReranker

        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9, 0.5, 0.3]
        mock_cross_encoder_cls.return_value = mock_model

        r = BEReranker(model_name="test-model")
        result = r.rerank("What is AI?", sample_chunks, top_k=2)

        for chunk in result:
            assert "rerank_score" in chunk.metadata

    @patch("src.infrastructure.rerankers.bge_reranker.CrossEncoder")
    def test_rerank_scores_are_normalized(self, mock_cross_encoder_cls):
        """Reranker normalizes scores to [0,1] range."""
        from src.infrastructure.rerankers.bge_reranker import BEReranker

        mock_model = MagicMock()
        mock_model.predict.return_value = [-5.0, 0.0, 5.0]
        mock_cross_encoder_cls.return_value = mock_model

        chunks = [
            Chunk(content=f"c{i}", metadata={}, chunk_index=i) for i in range(3)
        ]
        r = BEReranker(model_name="test-model")
        result = r.rerank("q", chunks, top_k=3)

        scores = [c.metadata["rerank_score"] for c in result]
        assert all(0.0 <= s <= 1.0 for s in scores)

    @patch("src.infrastructure.rerankers.bge_reranker.CrossEncoder")
    def test_rerank_preserves_original_content(
        self, mock_cross_encoder_cls, sample_chunks
    ):
        """Reranker doesn't lose chunk content."""
        from src.infrastructure.rerankers.bge_reranker import BEReranker

        mock_model = MagicMock()
        mock_model.predict.return_value = [0.1, 0.9, 0.5]
        mock_cross_encoder_cls.return_value = mock_model

        r = BEReranker(model_name="test-model")
        result = r.rerank("q", sample_chunks, top_k=3)

        contents = {c.content for c in result}
        expected = {c.content for c in sample_chunks}
        assert contents == expected

    @patch("src.infrastructure.rerankers.bge_reranker.CrossEncoder")
    def test_rerank_empty_chunks_returns_empty(self, mock_cross_encoder_cls):
        """Reranker handles empty input."""
        from src.infrastructure.rerankers.bge_reranker import BEReranker

        mock_model = MagicMock()
        mock_cross_encoder_cls.return_value = mock_model

        r = BEReranker(model_name="test-model")
        result = r.rerank("q", [], top_k=5)

        assert result == []
        mock_model.predict.assert_not_called()


class TestRerankerFactory:
    """Tests for the reranker factory."""

    @patch("src.infrastructure.rerankers.factory.get_settings")
    def test_factory_returns_none_when_disabled(self, mock_get_settings):
        from src.infrastructure.rerankers.factory import create_reranker

        mock_settings = MagicMock()
        mock_settings.ENABLE_RERANKING = False
        mock_get_settings.return_value = mock_settings

        result = create_reranker()
        assert result is None

    @patch("src.infrastructure.rerankers.factory.BEReranker")
    @patch("src.infrastructure.rerankers.factory.get_settings")
    def test_factory_returns_bereranker_when_enabled(
        self, mock_get_settings, mock_ber_cls
    ):
        from src.infrastructure.rerankers.factory import create_reranker

        mock_settings = MagicMock()
        mock_settings.ENABLE_RERANKING = True
        mock_settings.RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
        mock_get_settings.return_value = mock_settings

        result = create_reranker()
        mock_ber_cls.assert_called_once_with(model_name="BAAI/bge-reranker-v2-m3")
        assert result is mock_ber_cls.return_value
