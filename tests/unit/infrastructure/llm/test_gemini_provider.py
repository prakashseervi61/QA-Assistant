"""Unit tests for the Gemini LLM provider quota/rate-limit handling."""

import sys
from unittest.mock import MagicMock, PropertyMock, patch

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

    @pytest.mark.asyncio
    async def test_generate_stream_skips_part_less_final_chunk(
        self, mock_genai_client
    ):
        class PartLessChunk:
            @property
            def text(self):
                raise Exception(
                    "Invalid operation: The `response.text` quick accessor "
                    "requires the response to contain a valid `Part`, but none "
                    "were returned. The candidate's finish_reason is 1."
                )

        text_chunk = MagicMock()
        text_chunk.text = "full answer"
        mock_genai_client.generate_content.return_value = iter(
            [text_chunk, PartLessChunk()]
        )
        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")

        collected = [piece async for piece in provider.generate_stream("prompt")]
        assert collected == ["full answer"]

    @pytest.mark.asyncio
    async def test_generate_stream_skips_empty_chunks(self, mock_genai_client):
        first = MagicMock()
        first.text = "hello "
        empty = MagicMock()
        empty.text = ""
        last = MagicMock()
        last.text = "world"
        mock_genai_client.generate_content.return_value = iter([first, empty, last])

        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")
        collected = [piece async for piece in provider.generate_stream("prompt")]
        assert collected == ["hello ", "world"]


class TestGeminiProviderUsage:
    """GeminiProvider should expose token usage from the last response."""

    @pytest.mark.asyncio
    async def test_get_usage_returns_usage_metadata(self, mock_genai_client):
        usage_metadata = MagicMock()
        usage_metadata.prompt_token_count = 12
        usage_metadata.candidates_token_count = 34
        response = MagicMock()
        response.usage_metadata = usage_metadata
        response.text = "answer"
        mock_genai_client.generate_content.return_value = response

        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")
        result = await provider.generate("prompt")

        assert result == "answer"
        usage = await provider.get_usage()
        assert usage["prompt_tokens"] == 12
        assert usage["completion_tokens"] == 34

    @pytest.mark.asyncio
    async def test_get_usage_empty_before_any_generate(self, mock_genai_client):
        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")
        assert await provider.get_usage() == {}

    @pytest.mark.asyncio
    async def test_get_usage_empty_when_response_lacks_metadata(
        self, mock_genai_client
    ):
        response = MagicMock()
        response.usage_metadata = None
        response.text = "answer"
        mock_genai_client.generate_content.return_value = response

        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")
        await provider.generate("prompt")
        assert await provider.get_usage() == {}


class TestGeminiProviderJsonMode:
    """GeminiProvider.generate_json should request JSON mode from the API."""

    @pytest.mark.asyncio
    async def test_generate_json_passes_generation_config(self, mock_genai_client):
        response = MagicMock()
        response.text = '{"answer": "ok"}'
        mock_genai_client.generate_content.return_value = response

        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")
        result = await provider.generate_json("prompt")

        assert result == '{"answer": "ok"}'
        kwargs = mock_genai_client.generate_content.call_args.kwargs
        assert "generation_config" in kwargs
        assert kwargs["generation_config"] is not None

    @pytest.mark.asyncio
    async def test_generate_json_raises_quota_exceeded_on_429(self, mock_genai_client):
        mock_genai_client.generate_content.side_effect = Exception(
            "429 You exceeded your current quota."
        )
        provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")

        with pytest.raises(LLMQuotaExceededError):
            await provider.generate_json("prompt")
