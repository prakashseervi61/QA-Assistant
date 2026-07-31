"""Route-level tests for the chat API."""

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.use_cases.query_document import ConversationNotFoundError
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
    """Restore the module-level use cases after each test."""
    original_query = chat._query_use_case
    original_list = chat._conversation_list_use_case
    original_get = chat._conversation_get_use_case
    yield
    chat._query_use_case = original_query
    chat._conversation_list_use_case = original_list
    chat._conversation_get_use_case = original_get


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
        use_case = MagicMock()
        use_case.execute = AsyncMock(return_value=[conversation])
        chat.set_conversation_list_use_case(use_case)

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

    def test_get_conversations_returns_503_when_not_wired(self):
        chat._conversation_list_use_case = None

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
        use_case = MagicMock()
        use_case.execute = AsyncMock(return_value=[message])
        chat.set_conversation_get_use_case(use_case)

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
        use_case = MagicMock()
        use_case.execute = AsyncMock(
            side_effect=ConversationNotFoundError("Conversation not found: x")
        )
        chat.set_conversation_get_use_case(use_case)

        client = TestClient(_make_app())
        response = client.get(f"/api/conversations/{uuid4()}")

        assert response.status_code == 404

    def test_get_conversation_returns_400_for_malformed_uuid(self):
        use_case = MagicMock()
        use_case.execute = AsyncMock(
            side_effect=ValueError("Invalid conversation ID format: 'bad'")
        )
        chat.set_conversation_get_use_case(use_case)

        client = TestClient(_make_app())
        response = client.get("/api/conversations/not-a-uuid")

        assert response.status_code == 400

    def test_get_conversation_returns_503_when_not_wired(self):
        chat._conversation_get_use_case = None

        client = TestClient(_make_app())
        response = client.get(f"/api/conversations/{uuid4()}")

        assert response.status_code == 503
