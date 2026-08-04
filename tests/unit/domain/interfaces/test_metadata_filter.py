"""Tests for metadata filtering in VectorStore and RAGEngine."""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.value_objects.chunk import Chunk

# Valid UUIDs for mock data
_UUID1 = "00000000-0000-0000-0000-000000000001"
_DOC_UUID = "d1000000-0000-0000-0000-000000000001"


class TestVectorStoreMetadataFilter:
    """Tests that VectorStore methods accept metadata_filter."""

    def test_similarity_search_has_metadata_filter_param(self):
        """similarity_search should accept metadata_filter kwarg."""
        from src.domain.interfaces.vector_store import VectorStore

        sig = inspect.signature(VectorStore.similarity_search)
        assert "metadata_filter" in sig.parameters

    def test_hybrid_search_has_metadata_filter_param(self):
        """hybrid_search should accept metadata_filter kwarg."""
        from src.domain.interfaces.vector_store import VectorStore

        sig = inspect.signature(VectorStore.hybrid_search)
        assert "metadata_filter" in sig.parameters


class TestChromaStoreMetadataFilter:
    """Tests for ChromaStore metadata filtering."""

    @patch(
        "src.infrastructure.vector_store.chroma_store.chromadb.PersistentClient"
    )
    def test_similarity_search_passes_filter_to_chromadb(
        self, mock_client_cls
    ):
        """similarity_search passes 'where' to ChromaDB query."""
        from src.infrastructure.vector_store.chroma_store import ChromaStore

        mock_collection = MagicMock()
        mock_collection.count.return_value = 5
        mock_collection.query.return_value = {
            "ids": [[_UUID1]],
            "documents": [["doc1"]],
            "embeddings": [[[0.1]]],
            "metadatas": [
                [{"document_id": _DOC_UUID, "chunk_index": 0}]
            ],
            "distances": [[0.2]],
        }
        mock_client = MagicMock()
        mock_client.get_collection.return_value = (
            mock_collection
        )
        mock_client_cls.return_value = mock_client

        store = ChromaStore(persist_directory="/tmp/test")
        store._query_sync(
            query_embedding=[0.1, 0.2],
            k=3,
            collection_name="docs",
            metadata_filter={"document_id": "abc-123"},
        )

        call_kwargs = mock_collection.query.call_args[1]
        assert "where" in call_kwargs
        assert call_kwargs["where"] == {"document_id": "abc-123"}

    @patch(
        "src.infrastructure.vector_store.chroma_store.chromadb.PersistentClient"
    )
    def test_similarity_search_no_filter_omits_where(
        self, mock_client_cls
    ):
        """similarity_search omits 'where' when no filter is provided."""
        from src.infrastructure.vector_store.chroma_store import ChromaStore

        mock_collection = MagicMock()
        mock_collection.count.return_value = 5
        mock_collection.query.return_value = {
            "ids": [[_UUID1]],
            "documents": [["doc1"]],
            "embeddings": [[[0.1]]],
            "metadatas": [
                [{"document_id": _DOC_UUID, "chunk_index": 0}]
            ],
            "distances": [[0.2]],
        }
        mock_client = MagicMock()
        mock_client.get_collection.return_value = (
            mock_collection
        )
        mock_client_cls.return_value = mock_client

        store = ChromaStore(persist_directory="/tmp/test")
        store._query_sync(
            query_embedding=[0.1],
            k=3,
            collection_name="docs",
            metadata_filter=None,
        )

        call_kwargs = mock_collection.query.call_args[1]
        assert "where" not in call_kwargs

    @patch(
        "src.infrastructure.vector_store.chroma_store.chromadb.PersistentClient"
    )
    def test_hybrid_search_passes_filter_to_chromadb(
        self, mock_client_cls
    ):
        """hybrid_search passes 'where' to ChromaDB query."""
        from src.infrastructure.vector_store.chroma_store import ChromaStore

        mock_collection = MagicMock()
        mock_collection.count.return_value = 5
        mock_collection.query.return_value = {
            "ids": [[_UUID1]],
            "documents": [["doc1"]],
            "embeddings": [[[0.1]]],
            "metadatas": [
                [{"document_id": _DOC_UUID, "chunk_index": 0}]
            ],
            "distances": [[0.2]],
        }
        mock_client = MagicMock()
        mock_client.get_collection.return_value = (
            mock_collection
        )
        mock_client_cls.return_value = mock_client

        store = ChromaStore(persist_directory="/tmp/test")
        store._hybrid_search_sync(
            query_embedding=[0.1, 0.2],
            query_text="test query",
            k=3,
            collection_name="docs",
            metadata_filter={"document_id": "abc-123"},
        )

        call_kwargs = mock_collection.query.call_args[1]
        assert "where" in call_kwargs
        assert call_kwargs["where"] == {"document_id": "abc-123"}


class TestRAGEngineMetadataFilter:
    """Tests for RAGEngine metadata_filter parameter."""

    @pytest.fixture
    def mock_llm_provider(self):
        provider = AsyncMock()
        provider.generate = AsyncMock(return_value="Answer")
        provider.get_model_name = MagicMock(return_value="test-model")
        return provider

    @pytest.fixture
    def mock_embedding_provider(self):
        provider = AsyncMock()
        provider.embed = AsyncMock(return_value=[0.1, 0.2])
        return provider

    @pytest.fixture
    def mock_vector_store(self):
        store = AsyncMock()
        store.similarity_search = AsyncMock(
            return_value=[
                Chunk(
                    content="test",
                    metadata={"score": 0.9, "document_id": "d1"},
                    chunk_index=0,
                )
            ]
        )
        store.hybrid_search = AsyncMock(
            return_value=[
                Chunk(
                    content="test",
                    metadata={"score": 0.9, "document_id": "d1"},
                    chunk_index=0,
                )
            ]
        )
        store.get_collection_count = AsyncMock(return_value=1)
        return store

    @pytest.mark.asyncio
    @patch("src.application.services.rag_engine.get_settings")
    async def test_query_passes_metadata_filter(
        self,
        mock_get_settings,
        mock_llm_provider,
        mock_embedding_provider,
        mock_vector_store,
    ):
        from src.application.services.rag_engine import RAGEngine

        mock_settings = MagicMock()
        mock_settings.CHROMA_COLLECTION_NAME = "documents"
        mock_settings.ENABLE_HYBRID_SEARCH = False
        mock_get_settings.return_value = mock_settings

        engine = RAGEngine(
            mock_llm_provider, mock_embedding_provider, mock_vector_store
        )
        await engine.query(
            "What is AI?",
            metadata_filter={"document_id": "abc"},
        )

        call_kwargs = mock_vector_store.similarity_search.call_args[1]
        assert call_kwargs["metadata_filter"] == {
            "document_id": "abc",
        }

    @pytest.mark.asyncio
    @patch("src.application.services.rag_engine.get_settings")
    async def test_query_no_filter_defaults_none(
        self,
        mock_get_settings,
        mock_llm_provider,
        mock_embedding_provider,
        mock_vector_store,
    ):
        from src.application.services.rag_engine import RAGEngine

        mock_settings = MagicMock()
        mock_settings.CHROMA_COLLECTION_NAME = "documents"
        mock_settings.ENABLE_HYBRID_SEARCH = False
        mock_get_settings.return_value = mock_settings

        engine = RAGEngine(
            mock_llm_provider, mock_embedding_provider, mock_vector_store
        )
        await engine.query("What is AI?")

        call_kwargs = mock_vector_store.similarity_search.call_args[1]
        assert call_kwargs["metadata_filter"] is None

    @pytest.mark.asyncio
    @patch("src.application.services.rag_engine.get_settings")
    async def test_query_stream_passes_metadata_filter(
        self,
        mock_get_settings,
        mock_llm_provider,
        mock_embedding_provider,
        mock_vector_store,
    ):
        from src.application.services.rag_engine import RAGEngine

        mock_settings = MagicMock()
        mock_settings.CHROMA_COLLECTION_NAME = "documents"
        mock_settings.ENABLE_HYBRID_SEARCH = False
        mock_get_settings.return_value = mock_settings

        async def fake_stream(prompt):
            yield "ok"

        mock_llm_provider.generate_stream = fake_stream

        engine = RAGEngine(
            mock_llm_provider, mock_embedding_provider, mock_vector_store
        )
        async for _ in engine.query_stream(
            "test", metadata_filter={"document_id": "x"}
        ):
            pass

        call_kwargs = mock_vector_store.similarity_search.call_args[1]
        assert call_kwargs["metadata_filter"] == {"document_id": "x"}
