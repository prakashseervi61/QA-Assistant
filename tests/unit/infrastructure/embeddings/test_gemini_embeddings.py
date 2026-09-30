"""Unit tests for the Gemini embedding provider (``google-genai``)."""

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_genai_module():
    """Patch google.genai, reimport the provider, yield its models mock.

    This module binds ``genai`` at import time, so the patch has to be in
    place before the provider module is loaded.
    """
    genai_module = MagicMock()
    # `from google import genai` resolves to this mock, so self-reference it
    # to keep `genai.Client` pointing at the mock we control.
    genai_module.genai = genai_module
    client = genai_module.Client.return_value

    module_name = "src.infrastructure.embeddings.gemini_embeddings"
    with patch.dict(
        sys.modules, {"google": genai_module, "google.genai": genai_module}
    ):
        provider_module = importlib.import_module(module_name)
        importlib.reload(provider_module)
        yield client.models


def _response(*vectors):
    """Build a fake EmbedContentResponse carrying *vectors*."""
    response = MagicMock()
    response.embeddings = [MagicMock(values=list(v)) for v in vectors]
    return response


def _provider(api_key="test-key", **kwargs):
    """Build a provider from the currently-patched provider module."""
    import sys as _sys

    module = _sys.modules["src.infrastructure.embeddings.gemini_embeddings"]
    return module.GeminiEmbeddingProvider(api_key=api_key, **kwargs)


class TestGeminiEmbeddingProvider:
    def test_init_creates_client_with_api_key(self, mock_genai_module):
        provider = _provider(model="text-embedding-004")
        assert provider.get_embedding_dimension() == 768

    @pytest.mark.asyncio
    async def test_embed_returns_values_from_first_embedding(self, mock_genai_module):
        mock_genai_module.embed_content.return_value = _response([0.1, 0.2, 0.3])

        result = await _provider().embed("hello world")

        assert result == [0.1, 0.2, 0.3]
        kwargs = mock_genai_module.embed_content.call_args.kwargs
        assert kwargs["contents"] == "hello world"
        assert kwargs["model"] == "text-embedding-004"

    @pytest.mark.asyncio
    async def test_embed_batch_maps_every_embedding(self, mock_genai_module):
        mock_genai_module.embed_content.return_value = _response(
            [0.1, 0.2], [0.3, 0.4], [0.5, 0.6]
        )

        result = await _provider().embed_batch(["a", "b", "c"])

        assert result == [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        assert mock_genai_module.embed_content.call_args.kwargs["contents"] == [
            "a",
            "b",
            "c",
        ]

    @pytest.mark.asyncio
    async def test_embed_rejects_empty_text(self, mock_genai_module):
        with pytest.raises(ValueError):
            await _provider().embed("   ")

    @pytest.mark.asyncio
    async def test_embed_batch_rejects_empty_list(self, mock_genai_module):
        with pytest.raises(ValueError):
            await _provider().embed_batch([])

    @pytest.mark.asyncio
    async def test_embed_wraps_api_failure_in_runtime_error(self, mock_genai_module):
        mock_genai_module.embed_content.side_effect = Exception("upstream exploded")

        with pytest.raises(RuntimeError, match="Gemini embedding request failed"):
            await _provider().embed("hello")

    @pytest.mark.asyncio
    async def test_embed_batch_wraps_api_failure_in_runtime_error(
        self, mock_genai_module
    ):
        mock_genai_module.embed_content.side_effect = Exception("upstream exploded")

        with pytest.raises(RuntimeError, match="Gemini batch embedding request failed"):
            await _provider().embed_batch(["a"])
