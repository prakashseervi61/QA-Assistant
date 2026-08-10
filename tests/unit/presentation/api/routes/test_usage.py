"""Tests for the usage API endpoint."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.llm.token_tracker import TokenTracker


class TestUsageEndpoint:
    def test_usage_router_exists(self):
        """The usage router is importable and exposes GET /api/usage."""
        from src.presentation.api.routes.usage import router

        paths = [route.path for route in router.routes]
        assert "/api/usage" in paths

    @pytest.mark.asyncio
    async def test_usage_endpoint_returns_summary(self):
        """GET /api/usage returns usage summary JSON."""
        from src.presentation.api.routes.usage import get_usage

        mock_tracker = MagicMock()
        mock_tracker.get_summary.return_value = {
            "requests": 3,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "est_cost_usd": 0.001,
        }
        mock_tracker.get_recent.return_value = [{"prompt_tokens": 10}]

        response = await get_usage(tracker=mock_tracker, limit=5)
        assert response["requests"] == 3
        assert response["total_tokens"] == 150
        assert response["recent"] == [{"prompt_tokens": 10}]

    def test_usage_endpoint_via_test_client(self):
        """GET /api/usage works end-to-end with a real tracker."""
        from src.presentation.api.routes import usage

        original_tracker = usage._tracker
        usage._tracker = TokenTracker()
        usage._tracker.record_usage(
            model="gemini-2.5-flash", prompt_tokens=100, completion_tokens=50
        )
        try:
            app = FastAPI()
            app.include_router(usage.router)
            client = TestClient(app)

            response = client.get("/api/usage?limit=5")
            assert response.status_code == 200
            body = response.json()
            assert body["requests"] == 1
            assert body["prompt_tokens"] == 100
            assert body["total_tokens"] == 150
            assert len(body["recent"]) == 1
            assert body["recent"][0]["model"] == "gemini-2.5-flash"
        finally:
            usage._tracker = original_tracker
