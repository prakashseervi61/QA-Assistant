"""Unit tests for the RAGEngine service with mocked dependencies."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.services.rag_engine import RAGEngine, RAGQueryError
from src.domain.interfaces.llm_provider import LLMQuotaExceededError
from src.domain.value_objects.chunk import Chunk


def _content_only(events):
    """Drop additive ``stage`` trace events, leaving payload events only.

    ``query_stream`` now interleaves ``{"type": "stage", ...}`` events with
    raw text chunks. Tests that assert on answer content filter them out;
    the stage lifecycle is asserted explicitly in its own test.
    """
    return [
        e for e in events if not (isinstance(e, dict) and e.get("type") == "stage")
    ]


# Fixtures


@pytest.fixture
def mock_llm_provider():
    """Create a mock LLM provider."""
    provider = AsyncMock()
    provider.generate = AsyncMock(return_value="This is a generated answer.")
    provider.get_model_name = MagicMock(return_value="test-model")

    async def empty_stream(prompt):
        """Valid async generator so ``generate_stream`` can be iterated."""
        return
        yield  # pragma: no cover - makes this an async generator

    # generate_stream is an async-generator function: calling it must
    # return an async iterator, NOT a coroutine (an AsyncMock would
    # produce an un-awaited coroutine that ``async for`` cannot consume).
    provider.generate_stream = MagicMock(side_effect=empty_stream)
    return provider


@pytest.fixture
def mock_embedding_provider():
    """Create a mock embedding provider."""
    provider = AsyncMock()
    provider.embed = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4, 0.5])
    provider.embed_batch = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
    provider.get_embedding_dimension = MagicMock(return_value=5)
    return provider


@pytest.fixture
def mock_vector_store():
    """Create a mock vector store."""
    store = AsyncMock()
    store.similarity_search = AsyncMock(return_value=[])
    store.add_documents = AsyncMock()
    store.delete_by_metadata = AsyncMock()
    store.get_collection_count = AsyncMock(return_value=0)
    return store


@pytest.fixture
def sample_chunks():
    """Create sample chunks for retrieval."""
    return [
        Chunk(
            content="Machine learning is a subset of AI.",
            metadata={"filename": "ai_guide.pdf", "page": 1, "score": 0.9},
            chunk_index=0,
        ),
        Chunk(
            content="Neural networks are inspired by the brain.",
            metadata={"filename": "ai_guide.pdf", "page": 2, "score": 0.8},
            chunk_index=1,
        ),
        Chunk(
            content="Deep learning uses multiple layers.",
            metadata={"filename": "dl_basics.pdf", "page": 5, "score": 0.7},
            chunk_index=0,
        ),
    ]


@pytest.fixture
@patch("src.application.services.rag_engine.get_settings")
def rag_engine(
    mock_get_settings, mock_llm_provider, mock_embedding_provider, mock_vector_store
):
    """Create a RAGEngine with mocked dependencies."""
    mock_settings = MagicMock()
    mock_settings.CHROMA_COLLECTION_NAME = "documents"
    mock_settings.ENABLE_HYBRID_SEARCH = False
    mock_settings.ENABLE_QUERY_REWRITING = False
    mock_settings.QUERY_REWRITING_VARIANTS = 3
    # MagicMock returns truthy values for unknown attributes, so every
    # feature flag must be pinned to its OFF default explicitly.
    mock_settings.ENABLE_PARENT_CHILD = False
    mock_get_settings.return_value = mock_settings
    return RAGEngine(
        llm_provider=mock_llm_provider,
        embedding_provider=mock_embedding_provider,
        vector_store=mock_vector_store,
    )


# RAGEngine.query Tests


@pytest.mark.asyncio
class TestRAGEngineQuery:
    """Tests for the RAGEngine.query method."""

    async def test_query_returns_answer_string(self, rag_engine):
        result = await rag_engine.query("What is AI?")
        assert "answer" in result
        assert isinstance(result["answer"], str)

    async def test_query_returns_sources_list(self, rag_engine):
        result = await rag_engine.query("What is AI?")
        assert "sources" in result
        assert isinstance(result["sources"], list)

    async def test_query_returns_confidence_float(self, rag_engine):
        result = await rag_engine.query("What is AI?")
        assert "confidence" in result
        assert isinstance(result["confidence"], float)

    async def test_query_calls_embed_with_question(
        self, rag_engine, mock_embedding_provider
    ):
        await rag_engine.query("What is AI?")
        mock_embedding_provider.embed.assert_awaited_once_with("What is AI?")

    async def test_query_calls_vector_store_with_embedding(
        self, rag_engine, mock_vector_store
    ):
        await rag_engine.query("What is AI?")
        mock_vector_store.similarity_search.assert_awaited_once()

    async def test_query_calls_llm_generate(
        self, rag_engine, mock_llm_provider, mock_vector_store, sample_chunks
    ):
        mock_vector_store.similarity_search.return_value = sample_chunks
        await rag_engine.query("What is AI?")
        mock_llm_provider.generate.assert_awaited_once()

    async def test_query_with_custom_top_k(self, rag_engine, mock_vector_store):
        await rag_engine.query("test", top_k=10)
        call_kwargs = mock_vector_store.similarity_search.call_args
        assert call_kwargs.kwargs["k"] == 10

    async def test_query_default_top_k(self, rag_engine, mock_vector_store):
        await rag_engine.query("test")
        call_kwargs = mock_vector_store.similarity_search.call_args
        assert call_kwargs.kwargs["k"] == 5

    async def test_query_uses_correct_collection_name(
        self, rag_engine, mock_vector_store
    ):
        await rag_engine.query("test")
        call_kwargs = mock_vector_store.similarity_search.call_args
        assert call_kwargs.kwargs["collection_name"] == "documents"

    async def test_query_with_retrieved_chunks(
        self, rag_engine, mock_vector_store, sample_chunks, mock_llm_provider
    ):
        mock_vector_store.similarity_search.return_value = sample_chunks
        await rag_engine.query("What is AI?")
        call_args = mock_llm_provider.generate.call_args
        prompt = call_args.args[0]
        assert "ai_guide.pdf" in prompt
        assert "Machine learning" in prompt

    async def test_query_sources_match_chunks(
        self, rag_engine, mock_vector_store, sample_chunks
    ):
        mock_vector_store.similarity_search.return_value = sample_chunks
        result = await rag_engine.query("What is AI?")
        assert len(result["sources"]) == 3

    async def test_query_confidence_with_scores(
        self, rag_engine, mock_vector_store, sample_chunks
    ):
        mock_vector_store.similarity_search.return_value = sample_chunks
        result = await rag_engine.query("What is AI?")
        expected_confidence = (0.9 + 0.8 + 0.7) / 3
        assert abs(result["confidence"] - expected_confidence) < 0.001

    async def test_query_empty_chunks_returns_zero_confidence(
        self, rag_engine, mock_vector_store
    ):
        mock_vector_store.similarity_search.return_value = []
        result = await rag_engine.query("test")
        assert result["confidence"] == 0.0

    async def test_query_empty_chunks_returns_empty_sources(
        self, rag_engine, mock_vector_store
    ):
        mock_vector_store.similarity_search.return_value = []
        result = await rag_engine.query("test")
        assert result["sources"] == []

    async def test_query_wraps_exceptions_in_rag_query_error(
        self, rag_engine, mock_llm_provider, mock_vector_store, sample_chunks
    ):
        mock_vector_store.similarity_search.return_value = sample_chunks
        mock_llm_provider.generate.side_effect = RuntimeError("LLM exploded")
        with pytest.raises(RAGQueryError, match="Failed to process query"):
            await rag_engine.query("test")

    async def test_query_re_raises_quota_error_unwrapped(
        self, rag_engine, mock_llm_provider, mock_vector_store, sample_chunks
    ):
        mock_vector_store.similarity_search.return_value = sample_chunks
        mock_llm_provider.generate.side_effect = LLMQuotaExceededError("quota")
        with pytest.raises(LLMQuotaExceededError):
            await rag_engine.query("test")

    async def test_query_embedding_error_wrapped(
        self, rag_engine, mock_embedding_provider
    ):
        mock_embedding_provider.embed.side_effect = ConnectionError("Network down")
        with pytest.raises(RAGQueryError, match="Failed to process query"):
            await rag_engine.query("test")

    async def test_query_passes_llm_name_to_logger(
        self, rag_engine, mock_llm_provider, mock_vector_store, sample_chunks
    ):
        """Verify get_model_name is called (for logging)."""
        mock_vector_store.similarity_search.return_value = sample_chunks
        await rag_engine.query("test")
        mock_llm_provider.get_model_name.assert_called_once()

    # New: empty-retrieval behavior (no documents / no relevant context)

    async def test_query_no_documents_returns_upload_hint(
        self, rag_engine, mock_vector_store, mock_llm_provider
    ):
        mock_vector_store.similarity_search.return_value = []
        mock_vector_store.get_collection_count.return_value = 0
        result = await rag_engine.query("What is AI?")
        assert "No documents" in result["answer"]
        assert "upload" in result["answer"].lower()
        assert result["sources"] == []
        assert result["confidence"] == 0.0
        mock_llm_provider.generate.assert_not_awaited()

    async def test_query_no_relevant_context_message(
        self, rag_engine, mock_vector_store, mock_llm_provider
    ):
        mock_vector_store.similarity_search.return_value = []
        mock_vector_store.get_collection_count.return_value = 3
        result = await rag_engine.query("What is AI?")
        assert "relevant" in result["answer"].lower()
        assert result["sources"] == []
        assert result["confidence"] == 0.0
        mock_llm_provider.generate.assert_not_awaited()

    async def test_hybrid_search_used_when_enabled(
        self, rag_engine, mock_vector_store, sample_chunks
    ):
        """When ENABLE_HYBRID_SEARCH is True, hybrid_search is called."""
        rag_engine._settings.ENABLE_HYBRID_SEARCH = True
        rag_engine._embedding.embed = AsyncMock(return_value=[0.1, 0.2])
        mock_vector_store.hybrid_search = AsyncMock(return_value=sample_chunks)

        await rag_engine.query("What is AI?")
        mock_vector_store.hybrid_search.assert_awaited_once()

    async def test_similarity_search_used_when_hybrid_disabled(
        self, rag_engine, mock_vector_store, sample_chunks
    ):
        """When ENABLE_HYBRID_SEARCH is False (default), similarity_search is called."""
        rag_engine._settings.ENABLE_HYBRID_SEARCH = False
        mock_vector_store.similarity_search.return_value = sample_chunks

        await rag_engine.query("What is AI?")
        mock_vector_store.similarity_search.assert_awaited_once()

    async def test_query_with_query_rewriting_enabled(
        self, rag_engine, mock_vector_store, sample_chunks, mock_llm_provider
    ):
        """When query rewriting is enabled, multi-query retrieval is used."""
        rag_engine._settings.ENABLE_QUERY_REWRITING = True

        mock_rewriter = AsyncMock()
        mock_rewriter.rewrite = AsyncMock(
            return_value=["original", "variant1", "variant2"]
        )
        rag_engine._query_rewriter = mock_rewriter

        mock_vector_store.hybrid_search = AsyncMock(return_value=sample_chunks)
        mock_vector_store.similarity_search = AsyncMock(return_value=sample_chunks)
        rag_engine._settings.ENABLE_HYBRID_SEARCH = True

        result = await rag_engine.query("What is AI?")
        assert "answer" in result
        mock_rewriter.rewrite.assert_awaited_once()

    async def test_query_without_query_rewriting(
        self, rag_engine, mock_vector_store, sample_chunks
    ):
        """When query rewriting is disabled, single query path is used."""
        rag_engine._settings.ENABLE_QUERY_REWRITING = False
        rag_engine._query_rewriter = None

        await rag_engine.query("What is AI?")
        mock_vector_store.similarity_search.assert_awaited_once()

    # Parent-child retrieval (C2)

    async def test_query_parent_child_searches_child_collection_and_expands_parents(
        self, rag_engine, mock_vector_store, mock_llm_provider
    ):
        """With ENABLE_PARENT_CHILD, query() searches documents_child and
        expands the retrieved children to their parent chunks."""
        from uuid import uuid4

        rag_engine._settings.ENABLE_PARENT_CHILD = True

        parent = Chunk(
            id=uuid4(),
            content="Full parent context covering AI and ML concepts.",
            metadata={"filename": "ai.pdf", "chunk_type": "parent", "score": 0.9},
            chunk_index=0,
        )
        child = Chunk(
            id=uuid4(),
            content="ML is a subset of AI",
            metadata={
                "filename": "ai.pdf",
                "chunk_type": "child",
                "parent_id": str(parent.id),
                "score": 0.95,
            },
            chunk_index=0,
        )
        mock_vector_store.similarity_search.return_value = [child]
        mock_vector_store.get_documents_by_ids = AsyncMock(return_value=[parent])

        result = await rag_engine.query("What is ML?")

        assert "answer" in result
        # The search targets the child collection, not the main one.
        call_kwargs = mock_vector_store.similarity_search.call_args
        assert call_kwargs.kwargs["collection_name"] == "documents_child"
        # Parents were fetched via get_documents_by_ids.
        mock_vector_store.get_documents_by_ids.assert_awaited_once()
        ids_arg = mock_vector_store.get_documents_by_ids.call_args.args[0]
        assert ids_arg == [str(parent.id)]
        # The prompt context uses the parent content.
        prompt = mock_llm_provider.generate.call_args.args[0]
        assert "Full parent context" in prompt

    async def test_query_parent_child_without_parent_id_falls_back_to_children(
        self, rag_engine, mock_vector_store, mock_llm_provider
    ):
        """Children without parent_id metadata are used as-is (graceful)."""
        from uuid import uuid4

        rag_engine._settings.ENABLE_PARENT_CHILD = True

        plain_child = Chunk(
            id=uuid4(),
            content="Plain chunk without parent link.",
            metadata={"filename": "doc.txt", "score": 0.8},
            chunk_index=0,
        )
        mock_vector_store.similarity_search.return_value = [plain_child]

        result = await rag_engine.query("test")

        assert "answer" in result
        prompt = mock_llm_provider.generate.call_args.args[0]
        assert "Plain chunk" in prompt
        # No parent lookup was attempted.
        mock_vector_store.get_documents_by_ids.assert_not_awaited()

    # Query rewriting fallback (M1)

    async def test_query_rewrite_failure_falls_back_to_single_query(
        self, rag_engine, mock_vector_store, sample_chunks, mock_embedding_provider
    ):
        """If rewrite() raises, query() falls back to the original question."""
        rag_engine._settings.ENABLE_QUERY_REWRITING = True
        rag_engine._settings.ENABLE_HYBRID_SEARCH = False

        mock_rewriter = AsyncMock()
        mock_rewriter.rewrite = AsyncMock(side_effect=RuntimeError("LLM down"))
        rag_engine._query_rewriter = mock_rewriter

        mock_vector_store.similarity_search.return_value = sample_chunks

        result = await rag_engine.query("What is AI?")

        assert "answer" in result
        # Single-query path embedded and searched only the original question.
        mock_embedding_provider.embed.assert_awaited_once_with("What is AI?")
        assert mock_vector_store.similarity_search.await_count == 1

    async def test_query_rewrite_quota_error_propagates(
        self, rag_engine, mock_vector_store
    ):
        """LLMQuotaExceededError from rewrite() must propagate (429)."""
        rag_engine._settings.ENABLE_QUERY_REWRITING = True

        mock_rewriter = AsyncMock()
        mock_rewriter.rewrite = AsyncMock(side_effect=LLMQuotaExceededError("quota"))
        rag_engine._query_rewriter = mock_rewriter

        with pytest.raises(LLMQuotaExceededError):
            await rag_engine.query("test")

    async def test_query_rewrite_variant_search_failure_falls_back(
        self, rag_engine, mock_vector_store, sample_chunks, mock_embedding_provider
    ):
        """If a variant embed/search raises, query() falls back gracefully."""
        rag_engine._settings.ENABLE_QUERY_REWRITING = True
        rag_engine._settings.ENABLE_HYBRID_SEARCH = False

        mock_rewriter = AsyncMock()
        mock_rewriter.rewrite = AsyncMock(
            return_value=["original", "variant1", "variant2"]
        )
        rag_engine._query_rewriter = mock_rewriter

        mock_vector_store.similarity_search = AsyncMock(
            side_effect=[sample_chunks, RuntimeError("search boom"), sample_chunks]
        )

        result = await rag_engine.query("What is AI?")

        assert "answer" in result
        # Fallback re-embedded the original question.
        mock_embedding_provider.embed.assert_awaited_with("What is AI?")


# RAGEngine.query_stream Tests


@pytest.mark.asyncio
class TestRAGEngineQueryStream:
    """Tests for the RAGEngine.query_stream method."""

    async def test_stream_yields_chunks(
        self, rag_engine, mock_llm_provider, mock_vector_store, sample_chunks
    ):
        mock_vector_store.similarity_search.return_value = sample_chunks

        async def fake_stream(prompt):
            yield "Hello "
            yield "world"

        mock_llm_provider.generate_stream = fake_stream

        collected = []
        async for chunk in rag_engine.query_stream("test"):
            collected.append(chunk)

        assert _content_only(collected) == ["Hello ", "world"]

    async def test_stream_calls_embed(self, rag_engine, mock_embedding_provider):
        async def fake_stream(prompt):
            yield "ok"

        rag_engine._llm.generate_stream = fake_stream
        async for _ in rag_engine.query_stream("question"):
            pass
        mock_embedding_provider.embed.assert_awaited_once_with("question")

    async def test_stream_with_custom_top_k(self, rag_engine, mock_vector_store):
        async def fake_stream(prompt):
            yield "ok"

        rag_engine._llm.generate_stream = fake_stream
        async for _ in rag_engine.query_stream("test", top_k=3):
            pass
        call_kwargs = mock_vector_store.similarity_search.call_args
        assert call_kwargs.kwargs["k"] == 3

    async def test_stream_error_wrapped(
        self, rag_engine, mock_llm_provider, mock_vector_store, sample_chunks
    ):
        mock_vector_store.similarity_search.return_value = sample_chunks
        mock_llm_provider.generate_stream.side_effect = RuntimeError("boom")
        with pytest.raises(RAGQueryError, match="Failed to stream query"):
            async for _ in rag_engine.query_stream("test"):
                pass

    async def test_stream_re_raises_quota_error_unwrapped(
        self, rag_engine, mock_llm_provider, mock_vector_store, sample_chunks
    ):
        mock_vector_store.similarity_search.return_value = sample_chunks

        async def failing_stream(prompt):
            raise LLMQuotaExceededError("quota")
            yield  # pragma: no cover - unreachable, makes this a generator

        mock_llm_provider.generate_stream = failing_stream

        with pytest.raises(LLMQuotaExceededError):
            async for _ in rag_engine.query_stream("test"):
                pass

    async def test_stream_no_documents_yields_hint(
        self, rag_engine, mock_vector_store, mock_llm_provider
    ):
        mock_vector_store.similarity_search.return_value = []
        mock_vector_store.get_collection_count.return_value = 0
        collected = []
        async for chunk in rag_engine.query_stream("test"):
            collected.append(chunk)
        assert _content_only(collected) == [rag_engine.NO_DOCUMENTS_MESSAGE]
        mock_llm_provider.generate_stream.assert_not_called()

    async def test_stream_no_relevant_context_yields_hint(
        self, rag_engine, mock_vector_store, mock_llm_provider
    ):
        mock_vector_store.similarity_search.return_value = []
        mock_vector_store.get_collection_count.return_value = 3
        collected = []
        async for chunk in rag_engine.query_stream("test"):
            collected.append(chunk)
        assert _content_only(collected) == [rag_engine.NO_RELEVANT_CONTEXT_MESSAGE]
        mock_llm_provider.generate_stream.assert_not_called()

    async def test_stream_embedding_error_wrapped(
        self, rag_engine, mock_embedding_provider
    ):
        mock_embedding_provider.embed.side_effect = ValueError("bad input")
        with pytest.raises(RAGQueryError, match="Failed to stream query"):
            async for _ in rag_engine.query_stream("test"):
                pass

    async def test_stream_hybrid_search_when_enabled(
        self, rag_engine, mock_vector_store, sample_chunks
    ):
        """When ENABLE_HYBRID_SEARCH is True, hybrid_search is called in stream."""
        rag_engine._settings.ENABLE_HYBRID_SEARCH = True
        rag_engine._embedding.embed = AsyncMock(return_value=[0.1, 0.2])
        mock_vector_store.hybrid_search = AsyncMock(return_value=sample_chunks)

        async def fake_stream(prompt):
            yield "ok"

        rag_engine._llm.generate_stream = fake_stream

        async for _ in rag_engine.query_stream("test"):
            pass
        mock_vector_store.hybrid_search.assert_awaited_once()

    async def test_stream_with_query_rewriting_enabled(
        self, rag_engine, mock_vector_store, sample_chunks
    ):
        """When query rewriting is enabled in stream, multi-query retrieval is used."""
        rag_engine._settings.ENABLE_QUERY_REWRITING = True
        rag_engine._settings.ENABLE_HYBRID_SEARCH = False

        mock_rewriter = AsyncMock()
        mock_rewriter.rewrite = AsyncMock(return_value=["original", "variant1"])
        rag_engine._query_rewriter = mock_rewriter

        mock_vector_store.similarity_search = AsyncMock(return_value=sample_chunks)

        async def fake_stream(prompt):
            yield "streamed answer"

        rag_engine._llm.generate_stream = fake_stream

        collected = []
        async for chunk in rag_engine.query_stream("What is AI?"):
            collected.append(chunk)

        assert _content_only(collected) == ["streamed answer"]
        mock_rewriter.rewrite.assert_awaited_once()
        assert mock_vector_store.similarity_search.await_count == 2

    async def test_stream_rewrite_failure_falls_back_to_single_query(
        self, rag_engine, mock_vector_store, sample_chunks, mock_embedding_provider
    ):
        """If rewrite() raises, query_stream() falls back to the original."""
        rag_engine._settings.ENABLE_QUERY_REWRITING = True
        rag_engine._settings.ENABLE_HYBRID_SEARCH = False

        mock_rewriter = AsyncMock()
        mock_rewriter.rewrite = AsyncMock(side_effect=RuntimeError("LLM down"))
        rag_engine._query_rewriter = mock_rewriter

        mock_vector_store.similarity_search.return_value = sample_chunks

        async def fake_stream(prompt):
            yield "streamed answer"

        rag_engine._llm.generate_stream = fake_stream

        collected = []
        async for chunk in rag_engine.query_stream("What is AI?"):
            collected.append(chunk)

        assert _content_only(collected) == ["streamed answer"]
        mock_embedding_provider.embed.assert_awaited_once_with("What is AI?")
        assert mock_vector_store.similarity_search.await_count == 1

    async def test_stream_rewrite_quota_error_propagates(
        self, rag_engine, mock_vector_store
    ):
        """LLMQuotaExceededError from rewrite() propagates in stream mode."""
        rag_engine._settings.ENABLE_QUERY_REWRITING = True

        mock_rewriter = AsyncMock()
        mock_rewriter.rewrite = AsyncMock(side_effect=LLMQuotaExceededError("quota"))
        rag_engine._query_rewriter = mock_rewriter

        with pytest.raises(LLMQuotaExceededError):
            async for _ in rag_engine.query_stream("test"):
                pass

    async def test_stream_parent_child_searches_child_collection(
        self, rag_engine, mock_vector_store
    ):
        """query_stream() searches the child collection when enabled."""
        from uuid import uuid4

        rag_engine._settings.ENABLE_PARENT_CHILD = True

        parent = Chunk(
            id=uuid4(),
            content="Parent context for streaming.",
            metadata={"filename": "ai.pdf", "chunk_type": "parent", "score": 0.9},
            chunk_index=0,
        )
        child = Chunk(
            id=uuid4(),
            content="Child hit",
            metadata={
                "filename": "ai.pdf",
                "chunk_type": "child",
                "parent_id": str(parent.id),
                "score": 0.95,
            },
            chunk_index=0,
        )
        mock_vector_store.similarity_search.return_value = [child]
        mock_vector_store.get_documents_by_ids = AsyncMock(return_value=[parent])

        async def fake_stream(prompt):
            yield "streamed answer"

        rag_engine._llm.generate_stream = fake_stream

        collected = []
        async for chunk in rag_engine.query_stream("What is ML?"):
            collected.append(chunk)

        assert _content_only(collected) == ["streamed answer"]
        call_kwargs = mock_vector_store.similarity_search.call_args
        assert call_kwargs.kwargs["collection_name"] == "documents_child"
        mock_vector_store.get_documents_by_ids.assert_awaited_once()

    async def test_stream_emits_stage_events_in_order(
        self, rag_engine, mock_vector_store, sample_chunks
    ):
        """Stage events announce each pipeline step that runs, in order."""
        rag_engine._settings.ENABLE_QUERY_REWRITING = True
        rag_engine._settings.ENABLE_HYBRID_SEARCH = False

        mock_rewriter = AsyncMock()
        mock_rewriter.rewrite = AsyncMock(return_value=["original", "variant"])
        rag_engine._query_rewriter = mock_rewriter

        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = sample_chunks
        rag_engine._reranker = mock_reranker

        mock_vector_store.similarity_search = AsyncMock(return_value=sample_chunks)

        async def fake_stream(prompt):
            yield "ok"

        rag_engine._llm.generate_stream = fake_stream

        collected = []
        async for chunk in rag_engine.query_stream("What is AI?"):
            collected.append(chunk)

        stage_events = [
            e for e in collected if isinstance(e, dict) and e.get("type") == "stage"
        ]
        assert [e["stage"] for e in stage_events] == [
            "rewriting",
            "retrieving",
            "reranking",
            "generating",
        ]
        assert all("detail" in e for e in stage_events)
        mock_reranker.rerank.assert_called_once()


# RAGEngine._build_prompt Tests


class TestRAGEngineBuildPrompt:
    """Tests for the private _build_prompt method."""

    def test_prompt_contains_question(self, rag_engine):
        prompt = rag_engine._build_prompt("What is AI?", [])
        assert "What is AI?" in prompt

    def test_prompt_contains_context_from_chunks(self, rag_engine, sample_chunks):
        prompt = rag_engine._build_prompt("test", sample_chunks)
        assert "ai_guide.pdf" in prompt
        assert "dl_basics.pdf" in prompt
        assert "Machine learning" in prompt

    def test_prompt_shows_no_context_when_empty(self, rag_engine):
        prompt = rag_engine._build_prompt("test", [])
        assert "No relevant context found" in prompt

    def test_prompt_includes_page_info(self, rag_engine, sample_chunks):
        prompt = rag_engine._build_prompt("test", sample_chunks)
        assert "page 1" in prompt
        assert "page 2" in prompt

    def test_prompt_respects_max_context_chunks(self, rag_engine):
        many_chunks = [
            Chunk(
                content=f"chunk {i}",
                metadata={"filename": f"file{i}.pdf"},
                chunk_index=i,
            )
            for i in range(15)
        ]
        prompt = rag_engine._build_prompt("test", many_chunks)
        assert "file10.pdf" not in prompt
        assert "file9.pdf" in prompt

    def test_prompt_source_numbering(self, rag_engine, sample_chunks):
        prompt = rag_engine._build_prompt("test", sample_chunks)
        assert "[Source 1:" in prompt
        assert "[Source 2:" in prompt
        assert "[Source 3:" in prompt

    def test_prompt_chunk_without_page_shows_no_page_info(self, rag_engine):
        chunks = [Chunk(content="hello", metadata={"filename": "f.pdf"})]
        prompt = rag_engine._build_prompt("test", chunks)
        assert "page" not in prompt

    def test_prompt_chunk_unknown_filename(self, rag_engine):
        chunks = [Chunk(content="hello", metadata={})]
        prompt = rag_engine._build_prompt("test", chunks)
        assert "Unknown" in prompt


# RAGEngine._format_sources Tests


class TestRAGEngineFormatSources:
    """Tests for the private _format_sources method."""

    def test_format_sources_empty(self, rag_engine):
        assert rag_engine._format_sources([]) == []

    def test_format_sources_returns_list_of_dicts(self, rag_engine, sample_chunks):
        sources = rag_engine._format_sources(sample_chunks)
        assert isinstance(sources, list)
        assert all(isinstance(s, dict) for s in sources)

    def test_format_sources_has_expected_keys(self, rag_engine, sample_chunks):
        sources = rag_engine._format_sources(sample_chunks)
        for source in sources:
            assert "content" in source
            assert "metadata" in source
            assert "chunk_index" in source

    def test_format_sources_truncates_long_content(self, rag_engine):
        long_chunk = Chunk(content="x" * 1000, metadata={}, chunk_index=0)
        sources = rag_engine._format_sources([long_chunk])
        assert len(sources[0]["content"]) == 500

    def test_format_sources_preserves_metadata(self, rag_engine, sample_chunks):
        sources = rag_engine._format_sources(sample_chunks)
        assert sources[0]["metadata"]["filename"] == "ai_guide.pdf"

    def test_format_sources_preserves_chunk_index(self, rag_engine, sample_chunks):
        sources = rag_engine._format_sources(sample_chunks)
        assert sources[1]["chunk_index"] == 1


# RAGEngine._compute_confidence Tests


class TestRAGEngineComputeConfidence:
    """Tests for the private _compute_confidence method."""

    def test_compute_confidence_empty(self, rag_engine):
        assert rag_engine._compute_confidence([]) == 0.0

    def test_compute_confidence_single_chunk(self, rag_engine):
        chunk = Chunk(content="x", metadata={"score": 0.8})
        assert rag_engine._compute_confidence([chunk]) == 0.8

    def test_compute_confidence_multiple_chunks(self, rag_engine, sample_chunks):
        result = rag_engine._compute_confidence(sample_chunks)
        expected = (0.9 + 0.8 + 0.7) / 3
        assert abs(result - expected) < 0.001

    def test_compute_confidence_no_score_defaults_zero(self, rag_engine):
        chunk = Chunk(content="x", metadata={})
        assert rag_engine._compute_confidence([chunk]) == 0.0

    def test_compute_confidence_mixed_scores_and_missing(self, rag_engine):
        """Chunks without 'score' key default to 0.0 via get(), which IS numeric."""
        chunks = [
            Chunk(content="a", metadata={"score": 0.6}),
            Chunk(content="b", metadata={}),
            Chunk(content="c", metadata={"score": 0.8}),
        ]
        result = rag_engine._compute_confidence(chunks)
        # metadata.get('score', 0.0) returns 0.0 for chunk b,
        # so scores = [0.6, 0.0, 0.8]
        expected = (0.6 + 0.0 + 0.8) / 3
        assert abs(result - expected) < 0.001

    def test_compute_confidence_all_zero_scores(self, rag_engine):
        chunks = [
            Chunk(content="a", metadata={"score": 0.0}),
            Chunk(content="b", metadata={"score": 0.0}),
        ]
        assert rag_engine._compute_confidence(chunks) == 0.0

    def test_compute_confidence_integer_scores(self, rag_engine):
        chunk = Chunk(content="x", metadata={"score": 1})
        result = rag_engine._compute_confidence([chunk])
        assert result == 1.0

    def test_compute_confidence_non_numeric_score_ignored(self, rag_engine):
        chunks = [
            Chunk(content="a", metadata={"score": "invalid"}),
            Chunk(content="b", metadata={"score": 0.5}),
        ]
        result = rag_engine._compute_confidence(chunks)
        assert result == 0.5


# RAGEngine Prompt Template Tests


class TestRAGEnginePromptTemplate:
    """Verify the prompt template structure."""

    def test_prompt_template_has_placeholders(self):
        assert "{context}" in RAGEngine.PROMPT_TEMPLATE
        assert "{question}" in RAGEngine.PROMPT_TEMPLATE

    def test_prompt_template_has_instructions(self):
        assert "Instructions:" in RAGEngine.PROMPT_TEMPLATE

    def test_prompt_template_mentions_citations(self):
        assert "cite" in RAGEngine.PROMPT_TEMPLATE.lower()

    def test_prompt_template_has_context_label(self):
        assert "Context from documents" in RAGEngine.PROMPT_TEMPLATE


# RAGEngine Constants Tests


class TestRAGEngineConstants:
    """Verify class-level constants."""

    def test_default_top_k(self):
        assert RAGEngine.DEFAULT_TOP_K == 5

    def test_max_context_chunks(self):
        assert RAGEngine.MAX_CONTEXT_CHUNKS == 10


# RAGEngine Constructor Tests


@patch("src.application.services.rag_engine.get_settings")
class TestRAGEngineInit:
    """Tests for RAGEngine initialization."""

    def test_init_stores_providers(self, mock_get_settings):
        mock_settings = MagicMock()
        mock_settings.CHROMA_COLLECTION_NAME = "test"
        mock_get_settings.return_value = mock_settings

        llm = MagicMock()
        emb = MagicMock()
        vs = MagicMock()

        engine = RAGEngine(llm, emb, vs)
        assert engine._llm is llm
        assert engine._embedding is emb
        assert engine._vector_store is vs
        assert engine._query_rewriter is None

    def test_init_loads_settings(self, mock_get_settings):
        mock_settings = MagicMock()
        mock_settings.CHROMA_COLLECTION_NAME = "test"
        mock_get_settings.return_value = mock_settings

        engine = RAGEngine(MagicMock(), MagicMock(), MagicMock())
        mock_get_settings.assert_called_once()
        assert engine._settings is mock_settings
