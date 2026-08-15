"""Tests for prompt version selection in RAGEngine."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.services.rag_engine import RAGEngine
from src.domain.value_objects.chunk import Chunk
from src.infrastructure.config.settings import Settings
from src.infrastructure.llm.prompt_registry import PROMPT_VERSIONS

QUESTION = "What is RAG?"


def _chunks() -> list[Chunk]:
    """Return a non-empty chunk list so the pipeline reaches generation."""
    return [
        Chunk(
            content="RAG stands for retrieval augmented generation.",
            metadata={"filename": "doc.pdf", "page": 3, "score": 0.9},
            chunk_index=0,
        ),
    ]


def _context_block() -> str:
    return (
        "[Source 1: doc.pdf (page 3)]\nRAG stands for retrieval augmented generation."
    )


def _expected_prompt(version: str) -> str:
    return PROMPT_VERSIONS[version].format(context=_context_block(), question=QUESTION)


@pytest.fixture
def llm_provider():
    provider = AsyncMock()
    provider.generate = AsyncMock(return_value="answer")
    provider.get_model_name = MagicMock(return_value="test-model")
    return provider


@pytest.fixture
def embedding_provider():
    provider = AsyncMock()
    provider.embed = AsyncMock(return_value=[0.1, 0.2])
    return provider


@pytest.fixture
def vector_store():
    store = AsyncMock()
    store.similarity_search = AsyncMock(return_value=_chunks())
    store.get_collection_count = AsyncMock(return_value=1)
    return store


def _make_engine(
    llm_provider, embedding_provider, vector_store, **settings_kwargs
) -> RAGEngine:
    """Build an engine backed by a real Settings object."""
    with patch(
        "src.application.services.rag_engine.get_settings",
        return_value=Settings(**settings_kwargs),
    ):
        return RAGEngine(
            llm_provider=llm_provider,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
        )


@pytest.mark.asyncio
class TestPromptVersionSelection:
    """Default and configured prompt version selection."""

    async def test_default_settings_uses_v1_template(
        self, llm_provider, embedding_provider, vector_store
    ):
        engine = _make_engine(llm_provider, embedding_provider, vector_store)
        result = await engine.query(QUESTION)
        prompt = llm_provider.generate.call_args.args[0]
        assert prompt == _expected_prompt("v1")
        assert result["metadata"]["prompt_version"] == "v1"

    async def test_prompt_version_v2_uses_v2_template(
        self, llm_provider, embedding_provider, vector_store
    ):
        engine = _make_engine(
            llm_provider,
            embedding_provider,
            vector_store,
            PROMPT_VERSION="v2",
        )
        result = await engine.query(QUESTION)
        prompt = llm_provider.generate.call_args.args[0]
        assert prompt == _expected_prompt("v2")
        assert result["metadata"]["prompt_version"] == "v2"

    async def test_stream_done_event_carries_prompt_version(
        self, llm_provider, embedding_provider, vector_store
    ):
        engine = _make_engine(
            llm_provider,
            embedding_provider,
            vector_store,
            PROMPT_VERSION="v2",
        )
        manager = MagicMock()
        manager.check_input.return_value = {
            "flagged": False,
            "issues": [],
            "blocked": False,
        }
        manager.check_output.return_value = {
            "flagged": False,
            "issues": [],
            "groundedness": 1.0,
        }
        engine._guardrail_manager = manager

        async def fake_stream(prompt):
            assert prompt == _expected_prompt("v2")
            yield "streamed "

        llm_provider.generate_stream = fake_stream

        events = []
        async for event in engine.query_stream(QUESTION):
            events.append(event)

        done_events = [
            e for e in events if isinstance(e, dict) and e.get("type") == "done"
        ]
        assert done_events
        assert done_events[0]["prompt_version"] == "v2"
        assert done_events[0]["answer"] == "streamed "

    async def test_query_metadata_merges_prompt_version_with_guardrails(
        self, llm_provider, embedding_provider, vector_store
    ):
        engine = _make_engine(llm_provider, embedding_provider, vector_store)
        manager = MagicMock()
        manager.check_input.return_value = {
            "flagged": False,
            "issues": [],
            "blocked": False,
        }
        manager.check_output.return_value = {
            "flagged": False,
            "issues": [],
            "groundedness": 1.0,
        }
        engine._guardrail_manager = manager

        result = await engine.query(QUESTION)
        assert result["metadata"]["prompt_version"] == "v1"
        assert "guardrails" in result["metadata"]

    async def test_unknown_version_falls_back_to_v1_and_still_works(
        self, llm_provider, embedding_provider, vector_store
    ):
        engine = _make_engine(
            llm_provider,
            embedding_provider,
            vector_store,
            PROMPT_VERSION="does-not-exist",
        )
        result = await engine.query(QUESTION)
        prompt = llm_provider.generate.call_args.args[0]
        assert prompt == _expected_prompt("v1")
        # The metadata reports the configured version honestly, while the
        # pipeline falls back to the v1 template.
        assert result["metadata"]["prompt_version"] == "does-not-exist"
        assert "answer" in result
