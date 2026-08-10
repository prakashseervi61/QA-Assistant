"""Tests for the sliding window rate limiter."""

import time
from unittest.mock import MagicMock, patch

import pytest


class TestSlidingWindowRateLimiter:
    def test_allows_within_limit(self):
        """Requests within the limit are allowed."""
        from src.infrastructure.ratelimit.limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
        assert limiter.check("ip-1") is True
        assert limiter.check("ip-1") is True
        assert limiter.check("ip-1") is True
        assert limiter.check("ip-1") is False  # 4th exceeds

    def test_window_resets_after_time(self):
        """After the window passes, requests are allowed again."""
        from src.infrastructure.ratelimit.limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=1)
        assert limiter.check("ip-1") is True
        assert limiter.check("ip-1") is False
        time.sleep(1.1)
        assert limiter.check("ip-1") is True

    def test_keys_are_independent(self):
        """Different keys have independent limits."""
        from src.infrastructure.ratelimit.limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)
        assert limiter.check("ip-a") is True
        assert limiter.check("ip-b") is True
        assert limiter.check("ip-a") is False
        assert limiter.check("ip-b") is False

    def test_zero_max_requests_rejects_all(self):
        """max_requests=0 -> every request is rejected."""
        from src.infrastructure.ratelimit.limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(max_requests=0, window_seconds=60)
        assert limiter.check("ip-1") is False
        assert limiter.check("ip-2") is False

    def test_negative_max_requests_rejects_all(self):
        """Negative max_requests -> every request is rejected."""
        from src.infrastructure.ratelimit.limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(max_requests=-1, window_seconds=60)
        assert limiter.check("ip-1") is False

    def test_cleanup_removes_expired_keys(self):
        """_cleanup drops keys whose window fully expired."""
        from src.infrastructure.ratelimit.limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=0.1)
        assert limiter.check("ip-1") is True
        time.sleep(0.2)
        limiter._cleanup()
        assert "ip-1" not in limiter._timestamps

    def test_dependency_passes_when_disabled(self):
        """Rate limiting disabled -> dependency always passes."""
        from src.infrastructure.ratelimit.limiter import rate_limit_dependency

        with patch(
            "src.infrastructure.ratelimit.limiter.get_settings"
        ) as mock_settings:
            settings = MagicMock()
            settings.ENABLE_RATE_LIMITING = False
            mock_settings.return_value = settings

            import asyncio

            result = asyncio.run(rate_limit_dependency())
            assert result is None

    @pytest.mark.asyncio
    async def test_dependency_429_when_over_limit(self):
        """Rate limiting enabled + over limit -> 429."""
        from fastapi import HTTPException

        from src.infrastructure.ratelimit.limiter import rate_limit_dependency

        with (
            patch("src.infrastructure.ratelimit.limiter.get_settings") as mock_settings,
            patch("src.infrastructure.ratelimit.limiter._limiter") as mock_limiter,
        ):
            settings = MagicMock()
            settings.ENABLE_RATE_LIMITING = True
            settings.RATE_LIMIT_MAX_REQUESTS = 1
            settings.RATE_LIMIT_WINDOW_SECONDS = 60
            mock_settings.return_value = settings
            mock_limiter.check.return_value = False  # over limit

            class FakeRequest:
                client = MagicMock(host="127.0.0.1")

            with pytest.raises(HTTPException) as excinfo:
                await rate_limit_dependency(request=FakeRequest())
            assert excinfo.value.status_code == 429
