"""OpenAI LLM provider — real implementation."""

import logging
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from src.domain.interfaces.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """LLM provider using OpenAI's API (GPT-4o, GPT-4, etc.)."""

    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key)
        logger.info("OpenAI provider initialised (model=%s)", model)

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        try:
            response = await self._client.chat.completions.create(
                model=self._model, messages=messages, temperature=0.3, max_tokens=4096,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            raise RuntimeError(f"OpenAI API error: {exc}") from exc

    async def generate_stream(self, prompt: str, system_prompt: str | None = None) -> AsyncIterator[str]:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        try:
            stream = await self._client.chat.completions.create(
                model=self._model, messages=messages, temperature=0.3, max_tokens=4096, stream=True,
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            raise RuntimeError(f"OpenAI streaming error: {exc}") from exc

    def get_model_name(self) -> str:
        return self._model
