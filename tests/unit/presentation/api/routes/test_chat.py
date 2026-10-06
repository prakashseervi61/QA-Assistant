"""Route-level tests for the chat API."""

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.domain.entities.conversation import Conversation
from src.domain.entities.message import Message
from src.domain.interfaces.llm_provider import LLMQuotaExceededError
from src.presentation.api.routes import chat

QUOTA_MESSAGE = (
    "Your Gemini API key is out of quota or rate-limited for model "
    "'gemini-2.5-flash' (HTTP 429). Link a billing account in Google AI "
    "Studio (https://aistudio.google.com) or replace GEMINI_API_KEY / "
    "switch LLM_PROVIDER in your .env file."
)


@pytest.fixture(autouse=True)
def restore_use_cases():
    """Reset the dependency registries after each test.

    The registries are module-level singletons, so a test that wires one has to
    clear it or the next test inherits it. ``set(None)`` is how you un-register.
    """
    yield
    for registry in (
        chat._query_use_case,
        chat._conversation_repository,
    ):
        registry.set(None)


def _make_app() -> FastAPI:
    """Build an app with the chat router mounted under /api (as in app.py)."""
    app = FastAPI()
    app.include_router(chat.router, prefix="/api", tags=["chat"])
    return app


class TestQueryQuotaExceeded:
    """POST /api/query must return 429 when the LLM is out of quota."""

    def test_post_query_returns_429_on_quota_exceeded(self):
        use_case = MagicMock()
        use_case.execute = AsyncMock(side_effect=LLMQuotaExceededError(QUOTA_MESSAGE))
        chat.set_query_use_case(use_case)

        client = TestClient(_make_app())
        response = client.post("/api/query", json={"question": "What is AI?"})

        assert response.status_code == 429
        assert "out of quota" in response.json()["detail"]


class TestQueryStreamQuotaExceeded:
    """POST /api/query/stream must emit an error event on quota exceed."""

    def test_post_query_stream_emits_error_event(self):
        use_case = MagicMock()

        async def raising_stream(*args, **kwargs):
            raise LLMQuotaExceededError(QUOTA_MESSAGE)
            yield  # pragma: no cover - unreachable, makes this a generator

        use_case.execute_stream = raising_stream
        chat.set_query_use_case(use_case)

        client = TestClient(_make_app())
        with client.stream(
            "POST", "/api/query/stream", json={"question": "What is AI?"}
        ) as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

        events = []
        for block in body.split("\n\n"):
            if not block.startswith("data: "):
                continue
            payload = block.removeprefix("data: ")
            if payload == "[DONE]":
                events.append({"type": "[DONE]"})
            else:
                events.append(json.loads(payload))

        error_events = [event for event in events if event["type"] == "error"]
        assert len(error_events) == 1
        assert error_events[0]["type"] == "error"
        assert "out of quota" in error_events[0]["message"]
        assert events[-1] == {"type": "[DONE]"}


class TestListConversations:
    """GET /api/conversations returns recent conversations."""

    def test_get_conversations_returns_200_with_shape(self):
        conversation = Conversation(
            id=uuid4(),
            title="My conversation",
            messages=[Message(role="user", content="Hi")],
        )
        repo = MagicMock()
        repo.list_conversations = AsyncMock(return_value=[conversation])
        chat.set_conversation_repository(repo)

        client = TestClient(_make_app())
        response = client.get("/api/conversations")

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        item = payload[0]
        assert item["id"] == str(conversation.id)
        assert item["title"] == "My conversation"
        assert item["message_count"] == 1
        assert item["created_at"]
        assert item["updated_at"]

    def test_get_conversations_filters_empty_conversations(self):
        empty = Conversation(id=uuid4(), title="Empty placeholder")
        non_empty = Conversation(
            id=uuid4(),
            title="Has messages",
            messages=[Message(role="user", content="Hi")],
        )
        repo = MagicMock()
        repo.list_conversations = AsyncMock(return_value=[empty, non_empty])
        chat.set_conversation_repository(repo)

        client = TestClient(_make_app())
        response = client.get("/api/conversations")

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["id"] == str(non_empty.id)

    def test_get_conversations_passes_limit_to_repo(self):
        repo = MagicMock()
        repo.list_conversations = AsyncMock(return_value=[])
        chat.set_conversation_repository(repo)

        client = TestClient(_make_app())
        client.get("/api/conversations?limit=5")

        repo.list_conversations.assert_awaited_once_with(5)

    def test_get_conversations_returns_503_when_not_wired(self):
        chat._conversation_repository.set(None)

        client = TestClient(_make_app())
        response = client.get("/api/conversations")

        assert response.status_code == 503


class TestGetConversation:
    """GET /api/conversations/{id} returns conversation messages."""

    def test_get_conversation_returns_200_with_messages(self):
        message = Message(
            role="assistant",
            content="Answer",
            sources=[
                {
                    "content": "chunk text",
                    "metadata": {"score": 0.9, "chunk_index": 3},
                    "score": 0.9,
                    "chunk_index": 3,
                }
            ],
        )
        repo = MagicMock()
        repo.get_messages = AsyncMock(return_value=[message])
        chat.set_conversation_repository(repo)

        client = TestClient(_make_app())
        response = client.get(f"/api/conversations/{uuid4()}")

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        item = payload[0]
        assert item["role"] == "assistant"
        assert item["content"] == "Answer"
        assert item["sources"][0]["content"] == "chunk text"
        assert item["sources"][0]["score"] == 0.9
        assert item["sources"][0]["chunk_index"] == 3
        assert item["created_at"]

    def test_get_conversation_returns_404_for_unknown(self):
        repo = MagicMock()
        repo.get_messages = AsyncMock(side_effect=KeyError("missing"))
        chat.set_conversation_repository(repo)

        client = TestClient(_make_app())
        response = client.get(f"/api/conversations/{uuid4()}")

        assert response.status_code == 404

    def test_get_conversation_returns_400_for_malformed_uuid(self):
        repo = MagicMock()
        repo.get_messages = AsyncMock()
        chat.set_conversation_repository(repo)

        client = TestClient(_make_app())
        response = client.get("/api/conversations/not-a-uuid")

        assert response.status_code == 400
        repo.get_messages.assert_not_awaited()

    def test_get_conversation_returns_503_when_not_wired(self):
        chat._conversation_repository.set(None)

        client = TestClient(_make_app())
        response = client.get(f"/api/conversations/{uuid4()}")

        assert response.status_code == 503


class TestDeleteConversation:
    """DELETE /api/conversations/{id} removes a conversation."""

    def test_delete_conversation_returns_200(self):
        repo = MagicMock()
        repo.delete_conversation = AsyncMock(return_value=True)
        chat.set_conversation_repository(repo)

        conv_id = str(uuid4())
        client = TestClient(_make_app())
        response = client.delete(f"/api/conversations/{conv_id}")

        assert response.status_code == 200
        assert response.json() == {"deleted": True, "id": conv_id}

    def test_delete_conversation_returns_404_for_unknown(self):
        repo = MagicMock()
        repo.delete_conversation = AsyncMock(return_value=False)
        chat.set_conversation_repository(repo)

        conv_id = str(uuid4())
        client = TestClient(_make_app())
        response = client.delete(f"/api/conversations/{conv_id}")

        assert response.status_code == 404

    def test_delete_conversation_returns_400_for_malformed_uuid(self):
        repo = MagicMock()
        repo.delete_conversation = AsyncMock()
        chat.set_conversation_repository(repo)

        client = TestClient(_make_app())
        response = client.delete("/api/conversations/not-a-uuid")

        assert response.status_code == 400
        repo.delete_conversation.assert_not_awaited()

    def test_delete_conversation_returns_503_when_not_wired(self):
        chat._conversation_repository.set(None)

        client = TestClient(_make_app())
        response = client.delete(f"/api/conversations/{uuid4()}")

        assert response.status_code == 503
