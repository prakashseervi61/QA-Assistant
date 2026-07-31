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
