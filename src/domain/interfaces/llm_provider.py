from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMProvider(ABC):
    """Abstract base class for all LLM provider implementations."""

    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate a complete response from a prompt."""
        ...

    @abstractmethod
    async def generate_stream(
        self, prompt: str, system_prompt: str | None = None
    ) -> AsyncIterator[str]:
        """Generate a streaming response token by token."""
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the current model identifier."""
        ...
