"""DeepSeek LLM provider — OpenAI-compatible API."""

import logging
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from src.domain.interfaces.llm_provider import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"


class DeepSeekProvider(LLMProvider):
    """LLM provider using DeepSeek's OpenAI-compatible API.

    DeepSeek provides a generous free tier. The API is fully compatible
    with the OpenAI SDK — just a different base URL.

    Args:
        api_key:  DeepSeek API key.
        model:    Model identifier (default ``deepseek-chat``).
        base_url: API base URL (default ``https://api.deepseek.com/v1``).
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        logger.info("DeepSeek provider initialised (model=%s)", model)

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate a complete response using DeepSeek."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.3,
                max_tokens=4096,
            )
            content = response.choices[0].message.content or ""
            logger.debug("DeepSeek generated %d chars", len(content))
            return content
        except Exception as exc:
            logger.error("DeepSeek generation failed: %s", exc)
            raise RuntimeError(f"DeepSeek API error: {exc}") from exc

    async def generate_stream(
        self, prompt: str, system_prompt: str | None = None
    ) -> AsyncIterator[str]:
        """Generate a streaming response using DeepSeek."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.3,
                max_tokens=4096,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception as exc:
            logger.error("DeepSeek streaming failed: %s", exc)
            raise RuntimeError(f"DeepSeek streaming error: {exc}") from exc

    def get_model_name(self) -> str:
        return self._model
