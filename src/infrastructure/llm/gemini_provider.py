"""Google Gemini LLM provider — real implementation (``google-genai``)."""

import asyncio
import logging
from collections.abc import AsyncIterator

from src.domain.interfaces.llm_provider import LLMProvider, LLMQuotaExceededError

logger = logging.getLogger(__name__)

# Sentinel pushed by the streaming producer thread to signal completion.
_STREAM_DONE = object()

QUOTA_ERROR_MESSAGE = (
    "Your Gemini API key is out of quota or rate-limited for model "
    "'{model}' (HTTP 429). Link a billing account in Google AI Studio "
    "(https://aistudio.google.com) or replace GEMINI_API_KEY / switch "
    "LLM_PROVIDER in your .env file."
)


def _is_quota_error(exc: Exception) -> bool:
    """Detect HTTP 429 / RESOURCE_EXHAUSTED quota failures in an exception.

    ``google.genai`` raises ``errors.APIError`` subclasses that carry the HTTP
    status on ``.code``; the numeric and text fallbacks keep this working for
    transport-level errors that never got that far.
    """
    code = getattr(exc, "code", None)
    if code is None:
        code = getattr(exc, "status_code", None)
    text = str(exc)
    return code == 429 or "429" in text or "RESOURCE_EXHAUSTED" in text.upper()


class GeminiProvider(LLMProvider):
    """LLM provider using the Google Gemini API (``google-genai``)."""

    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._last_response = None
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("pip install google-genai")

        self._types = types
        # The new SDK scopes credentials to a client instance rather than
        # configuring the module globally.
        self._client = genai.Client(api_key=api_key)
        logger.info("Gemini provider initialised (model=%s)", model)

    def _config(self, system_prompt: str | None, **overrides):
        """Build a GenerateContentConfig, or None when nothing is set."""
        settings = dict(overrides)
        if system_prompt:
            settings["system_instruction"] = system_prompt
        if not settings:
            return None
        return self._types.GenerateContentConfig(**settings)

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        def _gen():
            return self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=self._config(system_prompt),
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

    async def get_usage(self) -> dict[str, object]:
        """Return token usage from the most recent generate call.

        Uses ``response.usage_metadata`` from the google-genai SDK
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

        Uses ``response_mime_type="application/json"`` so the model is
        constrained to emit valid JSON, which the structured-output parser
        can rely on.
        """

        def _gen():
            return self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=self._config(
                    system_prompt, response_mime_type="application/json"
                ),
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
        """Stream answer chunks from Gemini without blocking the event loop.

        The blocking SDK iteration runs entirely on a worker thread and
        hands chunks back through a queue, so the server stays responsive
        to other requests while an answer streams in.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[object] = asyncio.Queue()

        def _produce() -> None:
            """Blocking producer — runs on a worker thread."""
            try:
                stream = self._client.models.generate_content_stream(
                    model=self._model,
                    contents=prompt,
                    config=self._config(system_prompt),
                )
                last_chunk = None
                for chunk in stream:
                    last_chunk = chunk
                    try:
                        text = chunk.text
                    except Exception:
                        # A trailing part-less chunk (e.g. a safety stop) has
                        # no `.text` accessor; skip it and keep streaming.
                        continue
                    if text:
                        loop.call_soon_threadsafe(queue.put_nowait, text)

                # Recorded for logging/diagnostics only — the API response
                # shape is deliberately unchanged. Usage rides on the final
                # chunk of the stream.
                usage = getattr(last_chunk, "usage_metadata", None)
                if usage is not None:
                    logger.debug(
                        "Gemini stream usage (model=%s): prompt=%s completion=%s",
                        self._model,
                        getattr(usage, "prompt_token_count", None),
                        getattr(usage, "candidates_token_count", None),
                    )
            except Exception as exc:  # noqa: BLE001 - forwarded to consumer
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, _STREAM_DONE)

        producer = asyncio.create_task(asyncio.to_thread(_produce))
        try:
            while True:
                item = await queue.get()
                if item is _STREAM_DONE:
                    break
                if isinstance(item, Exception):
                    if _is_quota_error(item):
                        raise LLMQuotaExceededError(
                            QUOTA_ERROR_MESSAGE.format(model=self._model)
                        ) from item
                    raise RuntimeError(f"Gemini streaming error: {item}") from item
                yield item
        finally:
            if not producer.done():
                producer.cancel()

    def get_model_name(self) -> str:
        return self._model
