"""Unit tests for QueryDocumentUseCase quota/rate-limit handling."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.application.use_cases.query_document import QueryDocumentUseCase
from src.domain.entities.conversation import Conversation
from src.domain.interfaces.llm_provider import LLMQuotaExceededError


@pytest.fixture
def mock_rag_engine():
    """Create a mock RAG engine with default successful behaviour."""
    engine = MagicMock()
    engine.query = AsyncMock(
        return_value={"answer": "a", "sources": [], "confidence": 0.0}
    )
    engine.query_stream = MagicMock()
    return engine


@pytest.fixture
def mock_conversation_repo():
    """Create a mock conversation repository."""
    repo = MagicMock()
    repo.add_message = AsyncMock()
    repo.save_conversation = AsyncMock()
    repo.get_conversation = AsyncMock()
    return repo


@pytest.fixture
def use_case(mock_rag_engine, mock_conversation_repo):
    """Create a QueryDocumentUseCase with mocked dependencies."""
    return QueryDocumentUseCase(mock_rag_engine, mock_conversation_repo)


class TestExecuteQuotaPropagation:
    """execute() must re-raise LLMQuotaExceededError unwrapped."""

    @pytest.mark.asyncio
    async def test_execute_re_raises_quota_error_unwrapped(
        self, use_case, mock_rag_engine
    ):
        mock_rag_engine.query = AsyncMock(
            side_effect=LLMQuotaExceededError("quota exceeded")
        )

        with pytest.raises(LLMQuotaExceededError):
            await use_case.execute("What is AI?")


class TestExecuteStreamQuotaPropagation:
    """execute_stream() must re-raise LLMQuotaExceededError unwrapped."""

    @pytest.mark.asyncio
    async def test_execute_stream_re_raises_quota_error_unwrapped(
        self, use_case, mock_rag_engine
    ):
        async def failing_stream(question=None, top_k=None, metadata_filter=None):
            raise LLMQuotaExceededError("quota exceeded")
            yield  # pragma: no cover - unreachable, makes this a generator

        mock_rag_engine.query_stream = failing_stream

        with pytest.raises(LLMQuotaExceededError):
            async for _ in use_case.execute_stream("What is AI?"):
                pass


class TestExecuteStreamSoftSourcesFailure:
    """Quota errors on the post-stream sources fetch are soft failures."""

    @pytest.mark.asyncio
    async def test_execute_stream_soft_fails_quota_on_sources_fetch(
        self, use_case, mock_rag_engine, mock_conversation_repo
    ):
        async def ok_stream(question=None, top_k=None, metadata_filter=None):
            yield "Hello "
            yield "world"

        mock_rag_engine.query_stream = ok_stream
        mock_rag_engine.query = AsyncMock(
            side_effect=LLMQuotaExceededError("quota exceeded")
        )

        events = []
        async for event in use_case.execute_stream("What is AI?"):
            events.append(event)

        assert [event["type"] for event in events] == ["chunk", "chunk", "done"]
        done = events[-1]
        assert done["answer"] == "Hello world"
        assert done["sources"] == []
        assert done["confidence"] == 0.0

        # User + assistant messages persisted despite the quota error.
        assert mock_conversation_repo.add_message.call_count == 2
        # New conversation: empty save from _resolve_conversation + auto-title
        # save + final save with messages.
        assert mock_conversation_repo.save_conversation.call_count == 3


class TestAutoTitlePersistedOnFailure:
    """The auto-title must be persisted before the RAG engine runs, so it
    survives quota/rate-limit failures on the first question."""

    @pytest.mark.asyncio
    async def test_execute_quota_error_persists_auto_title(
        self, use_case, mock_rag_engine, mock_conversation_repo
    ):
        mock_rag_engine.query = AsyncMock(
            side_effect=LLMQuotaExceededError("quota exceeded")
        )

        with pytest.raises(LLMQuotaExceededError):
            await use_case.execute("What is AI?")

        # Two saves: empty title from _resolve_conversation, then the
        # auto-title save that must have happened before the quota error.
        assert mock_conversation_repo.save_conversation.call_count == 2
        saved = mock_conversation_repo.save_conversation.call_args[0][0]
        assert saved.title == "What is AI?"

    @pytest.mark.asyncio
    async def test_execute_stream_quota_error_persists_auto_title(
        self, use_case, mock_rag_engine, mock_conversation_repo
    ):
        async def failing_stream(question=None, top_k=None, metadata_filter=None):
            raise LLMQuotaExceededError("quota exceeded")
            yield  # pragma: no cover - unreachable, makes this a generator

        mock_rag_engine.query_stream = failing_stream

        with pytest.raises(LLMQuotaExceededError):
            async for _ in use_case.execute_stream("What is AI?"):
                pass

        # Two saves: empty title from _resolve_conversation, then the
        # auto-title save that must have happened before the quota error.
        assert mock_conversation_repo.save_conversation.call_count == 2
        saved = mock_conversation_repo.save_conversation.call_args[0][0]
        assert saved.title == "What is AI?"


class TestAutoTitle:
    """First question titles the conversation; existing titles preserved."""

    @pytest.mark.asyncio
    async def test_execute_sets_title_from_first_question(
        self, use_case, mock_conversation_repo
    ):
        long_question = "How do I " + "x" * 110

        await use_case.execute(long_question)

        saved = mock_conversation_repo.save_conversation.call_args[0][0]
        assert len(saved.title) <= 60
        assert saved.title.endswith("...")

    @pytest.mark.asyncio
    async def test_execute_collapses_whitespace_in_title(
        self, use_case, mock_conversation_repo
    ):
        await use_case.execute("What   is\n  the answer?")

        saved = mock_conversation_repo.save_conversation.call_args[0][0]
        assert saved.title == "What is the answer?"

    @pytest.mark.asyncio
    async def test_execute_preserves_existing_title(
        self, use_case, mock_conversation_repo
    ):
        conversation_id = str(uuid4())
        existing = Conversation(id=UUID(conversation_id), title="Existing title")
        mock_conversation_repo.get_conversation = AsyncMock(return_value=existing)

        await use_case.execute("New question", conversation_id=conversation_id)

        saved = mock_conversation_repo.save_conversation.call_args[0][0]
        assert saved.title == "Existing title"

    @pytest.mark.asyncio
    async def test_execute_stream_sets_title_from_first_question(
        self, use_case, mock_rag_engine, mock_conversation_repo
    ):
        async def ok_stream(question=None, top_k=None, metadata_filter=None):
            yield "Hello"
            yield "world"

        mock_rag_engine.query_stream = ok_stream
        mock_rag_engine.query = AsyncMock(
            return_value={"answer": "x", "sources": [], "confidence": 0.0}
        )

        question = "How do I " + "y" * 110
        async for _ in use_case.execute_stream(question):
            pass

        saved = mock_conversation_repo.save_conversation.call_args[0][0]
        assert saved.title == "How do I " + "y" * 48 + "..."
