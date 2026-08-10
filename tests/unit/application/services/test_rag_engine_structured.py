"""Tests for structured output path in RAGEngine."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.value_objects.chunk import Chunk


def _make_chunks() -> list[Chunk]:
    """Return a non-empty chunk list so the pipeline reaches generation."""
    return [
        Chunk(
            content="RAG stands for retrieval augmented generation.",
            metadata={"filename": "doc.pdf", "page": 3, "score": 0.9},
            chunk_index=0,
        ),
    ]


def _make_mocks(chunks: list[Chunk]):
    """Create mocked LLM, embedding, and vector store dependencies."""
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="regular answer")
    llm.get_model_name = MagicMock(return_value="m")
    llm.get_usage = AsyncMock(return_value={})

    embedding = AsyncMock()
    embedding.embed = AsyncMock(return_value=[0.1, 0.2])
    embedding.embed_batch = AsyncMock(return_value=[[0.1, 0.2]])
    embedding.get_embedding_dimension = MagicMock(return_value=2)

    store = AsyncMock()
    store.similarity_search = AsyncMock(return_value=chunks)
    store.hybrid_search = AsyncMock(return_value=chunks)
    store.get_collection_count = AsyncMock(return_value=0)
    return llm, embedding, store


@pytest.mark.asyncio
async def test_query_structured_output_returns_citations():
    """When use_structured_output=True, answer has structured citations."""
    from src.application.services.rag_engine import RAGEngine

    llm, embedding, store = _make_mocks(_make_chunks())

    engine = RAGEngine(
        llm_provider=llm,
        embedding_provider=embedding,
        vector_store=store,
    )

    with patch(
        "src.application.services.rag_engine.generate_structured_answer",
        new=AsyncMock(
            return_value=MagicMock(
                answer="structured answer",
                citations=[
                    MagicMock(
                        chunk_id="c1", source="doc.pdf", page=None, excerpt="text"
                    )
                ],
                confidence=0.9,
            )
        ),
    ) as mock_gen:
        result = await engine.query("What is RAG?", use_structured_output=True)
        mock_gen.assert_awaited_once()
        assert result["answer"] == "structured answer"
        assert len(result["citations"]) == 1
        assert result["citations"][0]["source"] == "doc.pdf"
        assert result["confidence"] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_query_default_does_not_call_structured():
    """Default path never calls structured output."""
    from src.application.services.rag_engine import RAGEngine

    llm, embedding, store = _make_mocks(_make_chunks())

    engine = RAGEngine(
        llm_provider=llm, embedding_provider=embedding, vector_store=store
    )

    with patch(
        "src.application.services.rag_engine.generate_structured_answer",
        new=AsyncMock(),
    ) as mock_gen:
        result = await engine.query("What is RAG?")
        mock_gen.assert_not_called()
        assert "answer" in result
