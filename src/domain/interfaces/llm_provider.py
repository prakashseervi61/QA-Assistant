from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMQuotaExceededError(RuntimeError):
    """Raised when the LLM provider is out of quota or rate-limited (HTTP 429)."""


class LLMProvider(ABC):
    """Abstract base class for all LLM provider implementations."""

    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate a complete response from a prompt."""
        ...

    @abstractmethod
    def generate_stream(
        self, prompt: str, system_prompt: str | None = None
    ) -> AsyncIterator[str]:
        """Generate a streaming response token by token.

        Async generator function — call once, then ``async for`` over the
        returned async iterator. Implementations must be async generators
        (``async def`` containing ``yield``); callers must not ``await``
        this method directly.
        """
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the current model identifier."""
        ...

    async def generate_json(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate a response constrained to JSON-only output.

        Default implementation falls back to :meth:`generate` with a
        JSON-mode system-prompt hint, so providers without native JSON
        mode still return parseable JSON (prompt-enforced). Providers
        whose model API supports native JSON mode (e.g. Gemini's
        ``response_mime_type="application/json"``) should override this
        to request it, improving parse reliability.
        """
        json_hint = system_prompt or (
            "Return ONLY valid JSON. No markdown, no prose around it."
        )
        return await self.generate(prompt, system_prompt=json_hint)

    async def get_usage(self) -> dict[str, object]:
        """Return token usage from the last generate call.

        Returns ``{"prompt_tokens": int, "completion_tokens": int}`` when
        the provider exposes usage metadata, or ``{}`` when unavailable.
        Concrete method so existing providers work unchanged.
        """
        return {}
