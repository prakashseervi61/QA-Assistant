"""Unit tests for the Gemini LLM provider quota/rate-limit handling."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from src.domain.interfaces.llm_provider import LLMQuotaExceededError
from src.infrastructure.llm.gemini_provider import GeminiProvider


@pytest.fixture
def mock_genai_client():
    """Patch google.generativeai with a fake module; yield the client mock."""
    genai_module = MagicMock()
    client = genai_module.GenerativeModel.return_value
    with patch.dict(sys.modules, {"google.generativeai": genai_module}):
        yield client


class TestGeminiProviderQuotaError:
    """GeminiProvider should raise LLMQuotaExceededError on HTTP 429."""

    @pytest.mark.asyncio
    async def test_generate_raises_quota_exceeded_on_429(self, mock_genai_client):
        mock_genai_client.generate_content.side_effect = Exception(
            "429 You exceeded your current quota, please check your plan "
            "and billing details."
        )
        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")

        with pytest.raises(LLMQuotaExceededError) as exc_info:
            await provider.generate("prompt")

        message = str(exc_info.value)
        assert "out of quota" in message
        assert "gemini-2.5-flash" in message

    @pytest.mark.asyncio
    async def test_generate_raises_quota_exceeded_on_resource_exhausted(
        self, mock_genai_client
    ):
        mock_genai_client.generate_content.side_effect = Exception(
            "RESOURCE_EXHAUSTED: Quota exceeded."
        )
        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")

        with pytest.raises(LLMQuotaExceededError):
            await provider.generate("prompt")

    @pytest.mark.asyncio
    async def test_generate_raises_runtime_error_on_other_error(
        self, mock_genai_client
    ):
        mock_genai_client.generate_content.side_effect = Exception(
            "Model not found for this API key."
        )
        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")

        with pytest.raises(RuntimeError, match="Gemini API error"):
            await provider.generate("prompt")

    @pytest.mark.asyncio
    async def test_generate_stream_raises_quota_exceeded_on_429(
        self, mock_genai_client
    ):
        mock_genai_client.generate_content.side_effect = Exception(
            "429 You exceeded your current quota."
        )
        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")

        with pytest.raises(LLMQuotaExceededError):
            async for _ in provider.generate_stream("prompt"):
                pass

    @pytest.mark.asyncio
    async def test_generate_stream_raises_runtime_error_on_other_error(
        self, mock_genai_client
    ):
        mock_genai_client.generate_content.side_effect = Exception(
            "Invalid argument supplied."
        )
        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")

        with pytest.raises(RuntimeError, match="Gemini streaming error"):
            async for _ in provider.generate_stream("prompt"):
                pass

    @pytest.mark.asyncio
    async def test_generate_stream_raises_quota_exceeded_mid_stream(
        self, mock_genai_client
    ):
        def chunks():
            chunk = MagicMock()
            chunk.text = "partial"
            yield chunk
            raise Exception("429 quota exceeded")

        mock_genai_client.generate_content.return_value = chunks()
        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")

        collected = []
        with pytest.raises(LLMQuotaExceededError):
            async for piece in provider.generate_stream("prompt"):
                collected.append(piece)

        # The token yielded before the quota failure is still delivered.
        assert collected == ["partial"]
