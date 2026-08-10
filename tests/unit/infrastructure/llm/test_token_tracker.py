"""Tests for token usage tracking."""

import pytest


class TestTokenTracker:
    """Tests for the in-memory TokenTracker."""

    def test_record_and_summary(self):
        """Records accumulate correctly."""
        from src.infrastructure.llm.token_tracker import TokenTracker

        tracker = TokenTracker()
        tracker.record_usage(
            model="gemini-2.5-flash", prompt_tokens=100, completion_tokens=50
        )
        tracker.record_usage(
            model="gemini-2.5-flash", prompt_tokens=200, completion_tokens=100
        )

        summary = tracker.get_summary()
        assert summary["requests"] == 2
        assert summary["prompt_tokens"] == 300
        assert summary["completion_tokens"] == 150
        assert summary["total_tokens"] == 450
        assert isinstance(summary["est_cost_usd"], float)
        assert summary["est_cost_usd"] > 0.0

    def test_recent_limit(self):
        """get_recent respects limit."""
        from src.infrastructure.llm.token_tracker import TokenTracker

        tracker = TokenTracker()
        for i in range(10):
            tracker.record_usage(model="m", prompt_tokens=i, completion_tokens=1)

        recent = tracker.get_recent(limit=3)
        assert len(recent) == 3
        # Most recent first
        assert recent[0]["prompt_tokens"] == 9

    def test_reset(self):
        """Reset clears all records."""
        from src.infrastructure.llm.token_tracker import TokenTracker

        tracker = TokenTracker()
        tracker.record_usage(model="m", prompt_tokens=10, completion_tokens=5)
        tracker.reset()
        summary = tracker.get_summary()
        assert summary["requests"] == 0
        assert summary["total_tokens"] == 0

    def test_cost_estimation(self):
        """Cost uses per-model prices."""
        from src.infrastructure.llm.token_tracker import TokenTracker

        tracker = TokenTracker(prices={"test-model": {"input": 1.0, "output": 2.0}})
        tracker.record_usage(
            model="test-model",
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
        )
        summary = tracker.get_summary()
        # 1M input tokens * $1.0/M + 1M output * $2.0/M = $3.0
        assert summary["est_cost_usd"] == pytest.approx(3.0)

    def test_unknown_model_cost_zero(self):
        """Unknown model doesn't crash cost estimation."""
        from src.infrastructure.llm.token_tracker import TokenTracker

        tracker = TokenTracker()
        tracker.record_usage(
            model="unknown-model", prompt_tokens=100, completion_tokens=50
        )
        summary = tracker.get_summary()
        assert summary["est_cost_usd"] == 0.0


class TestTrackingWrapper:
    """Tests for the provider wrapper."""

    @pytest.mark.asyncio
    async def test_wrapper_records_usage(self):
        """Wrapping a provider records usage after generate."""
        from unittest.mock import AsyncMock, MagicMock

        from src.infrastructure.llm.token_tracker import (
            TokenTracker,
            TrackingLLMProvider,
        )

        inner = AsyncMock()
        inner.generate = AsyncMock(return_value="answer")
        inner.get_model_name = MagicMock(return_value="test-model")
        inner.get_usage = AsyncMock(
            return_value={"prompt_tokens": 10, "completion_tokens": 5}
        )

        tracker = TokenTracker(prices={"test-model": {"input": 1.0, "output": 2.0}})
        wrapper = TrackingLLMProvider(inner, tracker)

        result = await wrapper.generate("prompt")
        assert result == "answer"
        summary = tracker.get_summary()
        assert summary["requests"] == 1
        assert summary["prompt_tokens"] == 10
        assert summary["completion_tokens"] == 5

    @pytest.mark.asyncio
    async def test_wrapper_handles_no_usage_data(self):
        """Wrapper works even when provider returns no usage."""
        from unittest.mock import AsyncMock, MagicMock

        from src.infrastructure.llm.token_tracker import (
            TokenTracker,
            TrackingLLMProvider,
        )

        inner = AsyncMock()
        inner.generate = AsyncMock(return_value="answer")
        inner.get_model_name = MagicMock(return_value="test-model")
        inner.get_usage = AsyncMock(return_value={})

        tracker = TokenTracker()
        wrapper = TrackingLLMProvider(inner, tracker)
        result = await wrapper.generate("prompt")
        assert result == "answer"
        summary = tracker.get_summary()
        assert summary["requests"] == 1
        assert summary["total_tokens"] == 0  # no usage data

    @pytest.mark.asyncio
    async def test_wrapper_records_with_request_id(self):
        """Recorded usage includes the request_id when provided."""
        from unittest.mock import AsyncMock, MagicMock

        from src.infrastructure.llm.token_tracker import (
            TokenTracker,
            TrackingLLMProvider,
        )

        inner = AsyncMock()
        inner.generate = AsyncMock(return_value="answer")
        inner.get_model_name = MagicMock(return_value="test-model")
        inner.get_usage = AsyncMock(
            return_value={"prompt_tokens": 10, "completion_tokens": 5}
        )

        tracker = TokenTracker()
        wrapper = TrackingLLMProvider(inner, tracker)

        await wrapper.generate("prompt", request_id="req-123")
        recent = tracker.get_recent(limit=1)
        assert recent[0]["request_id"] == "req-123"

    def test_getattr_delegates_unknown_attributes(self):
        """Unknown attributes are delegated to the wrapped provider."""
        from unittest.mock import MagicMock

        from src.infrastructure.llm.token_tracker import (
            TokenTracker,
            TrackingLLMProvider,
        )

        inner = MagicMock()
        inner.some_custom_flag = "custom-value"
        wrapper = TrackingLLMProvider(inner, TokenTracker())

        assert wrapper.some_custom_flag == "custom-value"

    def test_getattr_raises_attribute_error_when_uninitialized(self):
        """__getattr__ must not recurse infinitely before _provider is set.

        Regression: reading an unknown attribute on an uninitialized
        wrapper used to call self._provider, which re-entered __getattr__
        forever (RecursionError) instead of raising AttributeError.
        """
        from src.infrastructure.llm.token_tracker import TrackingLLMProvider

        wrapper = object.__new__(TrackingLLMProvider)
        with pytest.raises(AttributeError):
            _ = wrapper.some_unknown_attribute
