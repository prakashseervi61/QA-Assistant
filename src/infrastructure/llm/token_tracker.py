"""In-memory LLM token usage tracking with cost estimation."""

import logging
import time
from collections.abc import AsyncIterator

from src.domain.interfaces.llm_provider import LLMProvider

logger = logging.getLogger(__name__)

# Default per-model prices: USD per 1M tokens.
DEFAULT_PRICES: dict[str, dict[str, float]] = {
    "gemini-2.5-flash": {"input": 0.30, "output": 1.50},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
}


def _as_int(value: object) -> int:
    """Coerce a usage value to int, treating missing values as 0."""
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


class TokenTracker:
    """Thread-safe in-memory tracker for LLM token usage and cost.

    Records are appended atomically on the event loop; FastAPI runs a
    single event loop per process, so a plain list is safe.

    Args:
        prices: Per-model price table (USD per 1M tokens). Falls back to
            :data:`DEFAULT_PRICES` when omitted.
    """

    def __init__(self, prices: dict[str, dict[str, float]] | None = None) -> None:
        self._prices = prices or DEFAULT_PRICES
        self._records: list[dict[str, object]] = []

    def record_usage(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        request_id: str | None = None,
    ) -> None:
        """Record a single LLM call's usage."""
        record: dict[str, object] = {
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "timestamp": time.time(),
        }
        if request_id:
            record["request_id"] = request_id
        self._records.append(record)

    def _estimate_cost(self, record: dict[str, object]) -> float:
        model = record.get("model", "")
        price = self._prices.get(str(model))
        if not price:
            return 0.0
        input_tokens = _as_int(record.get("prompt_tokens"))
        output_tokens = _as_int(record.get("completion_tokens"))
        input_cost = (input_tokens / 1_000_000) * price.get("input", 0.0)
        output_cost = (output_tokens / 1_000_000) * price.get("output", 0.0)
        return round(input_cost + output_cost, 6)

    def get_summary(self) -> dict[str, object]:
        """Aggregate totals across all records."""
        requests = len(self._records)
        prompt = sum(_as_int(r.get("prompt_tokens")) for r in self._records)
        completion = sum(_as_int(r.get("completion_tokens")) for r in self._records)
        cost = sum(self._estimate_cost(r) for r in self._records)
        return {
            "requests": requests,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "est_cost_usd": round(cost, 6),
        }

    def get_recent(self, limit: int = 10) -> list[dict[str, object]]:
        """Return the most recent usage records (newest first)."""
        return list(reversed(self._records[-limit:]))

    def reset(self) -> None:
        """Clear all recorded usage."""
        self._records.clear()


class TrackingLLMProvider(LLMProvider):
    """Wraps an LLM provider, recording token usage after each call.

    Usage data comes from the wrapped provider's ``get_usage()`` (empty
    dict when unavailable). Streaming calls are delegated without
    tracking (token counts are only available on non-streaming
    responses). Unknown attributes are delegated to the wrapped provider.
    """

    def __init__(self, provider: LLMProvider, tracker: TokenTracker) -> None:
        self._provider = provider
        self._tracker = tracker

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: object,
    ) -> str:
        request_id = kwargs.pop("request_id", None)
        if not isinstance(request_id, str):
            request_id = None
        result = await self._provider.generate(
            prompt, system_prompt=system_prompt, **kwargs
        )
        try:
            usage = await self._provider.get_usage()
            self._tracker.record_usage(
                model=self._provider.get_model_name(),
                prompt_tokens=_as_int(usage.get("prompt_tokens")),
                completion_tokens=_as_int(usage.get("completion_tokens")),
                request_id=request_id,
            )
        except Exception as exc:
            logger.warning("Failed to record token usage: %s", exc)
        return result

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        async for chunk in self._provider.generate_stream(
            prompt, system_prompt=system_prompt
        ):
            yield chunk

    def get_model_name(self) -> str:
        return self._provider.get_model_name()

    async def get_usage(self) -> dict[str, object]:
        return await self._provider.get_usage()

    def __getattr__(self, name: str) -> object:
        # Delegate unknown attributes to the wrapped provider. Use
        # object.__getattribute__ so a missing/incomplete ``_provider``
        # raises a clean AttributeError instead of recursing back into
        # __getattr__ forever (e.g. during unpickling before __init__).
        try:
            provider = object.__getattribute__(self, "_provider")
        except AttributeError:
            raise AttributeError(name) from None
        return getattr(provider, name)
