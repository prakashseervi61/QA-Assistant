"""Anthropic Claude LLM provider — real implementation."""

import logging
from collections.abc import AsyncIterator

from src.domain.interfaces.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """LLM provider using Anthropic's Claude API."""

    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        try:
            import anthropic

            self._client = anthropic.AsyncAnthropic(api_key=api_key)
            logger.info("Anthropic provider initialised (model=%s)", model)
        except ImportError:
            raise ImportError("pip install anthropic")

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        try:
            kwargs = {
                "model": self._model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                kwargs["system"] = system_prompt
            response = await self._client.messages.create(**kwargs)
            return response.content[0].text if response.content else ""
        except Exception as exc:
            raise RuntimeError(f"Anthropic API error: {exc}") from exc

    async def generate_stream(
        self, prompt: str, system_prompt: str | None = None
    ) -> AsyncIterator[str]:
        try:
            kwargs = {
                "model": self._model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                kwargs["system"] = system_prompt
            async with self._client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            raise RuntimeError(f"Anthropic streaming error: {exc}") from exc

    def get_model_name(self) -> str:
        return self._model
