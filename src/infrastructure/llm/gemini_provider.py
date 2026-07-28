"""Google Gemini LLM provider — real implementation."""

import asyncio
import logging
from collections.abc import AsyncIterator

from src.domain.interfaces.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """LLM provider using Google Gemini API."""

    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self._client = genai.GenerativeModel(model)
            logger.info("Gemini provider initialised (model=%s)", model)
        except ImportError:
            raise ImportError("pip install google-generativeai")

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        def _gen():
            kwargs = {}
            if system_prompt:
                kwargs["system_instruction"] = system_prompt
            return self._client.generate_content(prompt, **kwargs).text or ""
        try:
            return await asyncio.to_thread(_gen)
        except Exception as exc:
            raise RuntimeError(f"Gemini API error: {exc}") from exc

    async def generate_stream(self, prompt: str, system_prompt: str | None = None) -> AsyncIterator[str]:
        def _stream():
            kwargs = {}
            if system_prompt:
                kwargs["system_instruction"] = system_prompt
            return self._client.generate_content(prompt, stream=True, **kwargs)
        try:
            response = await asyncio.to_thread(_stream)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            raise RuntimeError(f"Gemini streaming error: {exc}") from exc

    def get_model_name(self) -> str:
        return self._model
