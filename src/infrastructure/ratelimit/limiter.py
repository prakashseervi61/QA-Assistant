"""In-memory sliding-window rate limiter.

Rate limiting is gated by ``settings.ENABLE_RATE_LIMITING`` (off by
default). The limiter tracks request timestamps per key (client IP),
prunes expired entries on every check, and drops keys whose window has
fully expired so memory stays bounded.
"""

import threading
import time

from fastapi import HTTPException, Request

from src.infrastructure.config.settings import Settings, get_settings

# Trigger a full sweep when the key table grows beyond this many entries.
_MAX_KEYS = 1024


class SlidingWindowRateLimiter:
    """A sliding-window rate limiter keyed by an arbitrary string.

    ``check(key)`` records a request for ``key`` and returns True while the
    number of requests inside the current window is below ``max_requests``,
    and False once the limit is reached (window slides with each request).
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        """Initialise the limiter with the given limit and window size."""
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """Record a request for ``key`` and return True if it is allowed."""
        if self.max_requests <= 0:
            # Misconfigured (or intentionally closed) limiter: reject all.
            return False
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            # The key table is sized and swept under the lock so the
            # length check cannot race with other check() calls.
            if len(self._timestamps) > _MAX_KEYS:
                self._cleanup_unlocked(now, cutoff)

            timestamps = self._timestamps.get(key)
            if timestamps is None:
                self._timestamps[key] = [now]
                return True

            # Prune timestamps that have fallen out of the window.
            timestamps = [t for t in timestamps if t > cutoff]
            if not timestamps:
                # Window fully expired — drop the key and start fresh.
                del self._timestamps[key]
                self._timestamps[key] = [now]
                return True

            if len(timestamps) >= self.max_requests:
                self._timestamps[key] = timestamps
                return False

            timestamps.append(now)
            self._timestamps[key] = timestamps
            return True

    def _cleanup_unlocked(self, now: float, cutoff: float) -> None:
        """Drop keys whose most recent request is outside the window.

        The caller must already hold ``self._lock``.
        """
        for key in [
            key for key, ts in self._timestamps.items() if not ts or ts[-1] <= cutoff
        ]:
            del self._timestamps[key]

    def _cleanup(self) -> None:
        """Drop keys whose most recent request is outside the window.

        Keeps the key table from growing without bound when many distinct
        clients make one-off requests.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            self._cleanup_unlocked(now, cutoff)


# Module-level singleton; recreated lazily from settings on first use.
_limiter: SlidingWindowRateLimiter | None = None


def _get_limiter(settings: Settings) -> SlidingWindowRateLimiter:
    """Return the module-level limiter, creating it on first use."""
    global _limiter
    if _limiter is None:
        _limiter = SlidingWindowRateLimiter(
            max_requests=settings.RATE_LIMIT_MAX_REQUESTS,
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        )
    return _limiter


async def rate_limit_dependency(request: Request = None) -> None:
    """FastAPI dependency enforcing the per-client-IP sliding window.

    No-op when ``ENABLE_RATE_LIMITING`` is False (the default). When
    enabled, raises ``HTTPException(429)`` once the client exceeds the
    configured limit within the window.

    Note: the ``Request`` parameter carries a default of None so the
    dependency can be invoked directly (e.g. in tests); FastAPI still
    injects the real request because the annotation is exactly ``Request``.
    """
    settings = get_settings()
    if not settings.ENABLE_RATE_LIMITING:
        return None

    limiter = _get_limiter(settings)
    if request is None or request.client is None:
        client_ip = "unknown"
    else:
        client_ip = request.client.host

    if not limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    return None
