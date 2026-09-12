"""Google Gemini LLM provider — real implementation."""

import asyncio
import logging
from collections.abc import AsyncIterator

from src.domain.interfaces.llm_provider import LLMProvider, LLMQuotaExceededError

logger = logging.getLogger(__name__)

QUOTA_ERROR_MESSAGE = (
    "Your Gemini API key is out of quota or rate-limited for model "
    "'{model}' (HTTP 429). Link a billing account in Google AI Studio "
    "(https://aistudio.google.com) or replace GEMINI_API_KEY / switch "
    "LLM_PROVIDER in your .env file."
)


def _is_quota_error(exc: Exception) -> bool:
    """Detect HTTP 429 / RESOURCE_EXHAUSTED quota failures in an exception.

    Matches on the numeric HTTP status code ``429`` (either on the
    exception object itself or in its text) or the gRPC status
    ``RESOURCE_EXHAUSTED``, avoiding false positives on the word "quota"
    appearing in unrelated error bodies.
    """
    text = str(exc)
    return (
        getattr(exc, "status_code", None) == 429
        or "429" in text
        or "RESOURCE_EXHAUSTED" in text.upper()
    )


class GeminiProvider(LLMProvider):
    """LLM provider using Google Gemini API."""

    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._last_response = None
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
            return self._client.generate_content(prompt, **kwargs)

        try:
            response = await asyncio.to_thread(_gen)
            self._last_response = response
            return response.text or ""
        except Exception as exc:
            if _is_quota_error(exc):
                raise LLMQuotaExceededError(
                    QUOTA_ERROR_MESSAGE.format(model=self._model)
                ) from exc
            raise RuntimeError(f"Gemini API error: {exc}") from exc

    async def get_usage(self) -> dict[str, object]:
        """Return token usage from the most recent generate call.

        Uses ``response.usage_metadata`` from the google-generativeai SDK
        (``prompt_token_count`` / ``candidates_token_count``). Returns an
        empty dict when no response has been produced yet or the response
        carries no usage metadata.
        """
        response = self._last_response
        if response is None:
            return {}
        usage_metadata = getattr(response, "usage_metadata", None)
        if usage_metadata is None:
            return {}
        return {
            "prompt_tokens": getattr(usage_metadata, "prompt_token_count", 0),
            "completion_tokens": getattr(usage_metadata, "candidates_token_count", 0),
        }

    async def generate_json(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate a response with JSON mode enforced by the model API.

        Uses ``response_mime_type="application/json"`` (supported by
        google-generativeai >= 0.8) so the model is constrained to emit
        valid JSON, which the structured-output parser can rely on.
        """
        import google.generativeai as genai

        def _gen():
            kwargs = {}
            if system_prompt:
                kwargs["system_instruction"] = system_prompt
            config = genai.types.GenerationConfig(response_mime_type="application/json")
            return self._client.generate_content(
                prompt, generation_config=config, **kwargs
            )

        try:
            response = await asyncio.to_thread(_gen)
            self._last_response = response
            return response.text or ""
        except Exception as exc:
            if _is_quota_error(exc):
                raise LLMQuotaExceededError(
                    QUOTA_ERROR_MESSAGE.format(model=self._model)
                ) from exc
            raise RuntimeError(f"Gemini API error: {exc}") from exc

    async def generate_stream(
        self, prompt: str, system_prompt: str | None = None
    ) -> AsyncIterator[str]:
        def _stream():
            kwargs = {}
            if system_prompt:
                kwargs["system_instruction"] = system_prompt
            return self._client.generate_content(prompt, stream=True, **kwargs)

        try:
            response = await asyncio.to_thread(_stream)
            for chunk in response:
                try:
                    text = chunk.text
                except Exception:
                    continue
                if text:
                    yield text
        except Exception as exc:
            if _is_quota_error(exc):
                raise LLMQuotaExceededError(
                    QUOTA_ERROR_MESSAGE.format(model=self._model)
                ) from exc
            raise RuntimeError(f"Gemini streaming error: {exc}") from exc

    def get_model_name(self) -> str:
        return self._model
