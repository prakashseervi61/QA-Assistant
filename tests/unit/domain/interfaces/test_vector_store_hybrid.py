"""Tests for the VectorStore hybrid_search interface extension."""

from unittest.mock import MagicMock, patch

import pytest

# Valid UUIDs for mock data
_UUID1 = "00000000-0000-0000-0000-000000000001"
_UUID2 = "00000000-0000-0000-0000-000000000002"
_DOC_UUID = "d1000000-0000-0000-0000-000000000001"


class TestVectorStoreHybridSearch:
    """Tests for hybrid_search on VectorStore."""

    def test_hybrid_search_exists(self):
        """VectorStore should define hybrid_search."""
        from src.domain.interfaces.vector_store import VectorStore

        assert hasattr(VectorStore, "hybrid_search")

    def test_vector_store_hybrid_search_is_not_abstract(self):
        """hybrid_search must NOT be abstract — it has a default impl."""
        from src.domain.interfaces.vector_store import VectorStore

        method = getattr(VectorStore, "hybrid_search")
        assert not getattr(method, "__isabstractmethod__", False)

    @patch(
        "src.infrastructure.vector_store.chroma_store.chromadb.PersistentClient"
    )
    def test_chroma_hybrid_search_with_both_params(self, mock_client_cls):
        """hybrid_search passes both query_texts and query_embeddings."""
        from src.infrastructure.vector_store.chroma_store import ChromaStore

        mock_collection = MagicMock()
        mock_collection.count.return_value = 5
        mock_collection.query.return_value = {
            "ids": [[_UUID1]],
            "documents": [["doc1"]],
            "embeddings": [[[0.1, 0.2]]],
            "metadatas": [
                [{"document_id": _DOC_UUID, "chunk_index": 0}]
            ],
            "distances": [[0.3]],
        }
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_client_cls.return_value = mock_client

        store = ChromaStore(persist_directory="/tmp/test")
        result = store._hybrid_search_sync(
            query_embedding=[0.1, 0.2],
            query_text="test query",
            k=3,
            collection_name="docs",
        )

        mock_collection.query.assert_called_once()
        call_kwargs = mock_collection.query.call_args[1]
        assert "query_embeddings" in call_kwargs
        assert "query_texts" in call_kwargs
        assert call_kwargs["query_texts"] == ["test query"]
        assert len(result) == 1

    @patch(
        "src.infrastructure.vector_store.chroma_store.chromadb.PersistentClient"
    )
    def test_chroma_hybrid_search_empty_collection(self, mock_client_cls):
        """hybrid_search returns [] for empty collection."""
        from src.infrastructure.vector_store.chroma_store import ChromaStore

        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_client_cls.return_value = mock_client

        store = ChromaStore(persist_directory="/tmp/test")
        result = store._hybrid_search_sync(
            query_embedding=[0.1], query_text="q", k=5, collection_name="c"
        )
        assert result == []

    @patch(
        "src.infrastructure.vector_store.chroma_store.chromadb.PersistentClient"
    )
    def test_chroma_hybrid_search_falls_back_to_dense(self, mock_client_cls):
        """When query_text is empty, falls back to pure dense search."""
        from src.infrastructure.vector_store.chroma_store import ChromaStore

        mock_collection = MagicMock()
        mock_collection.count.return_value = 5
        mock_collection.query.return_value = {
            "ids": [[_UUID1]],
            "documents": [["d"]],
            "embeddings": [[[0.1]]],
            "metadatas": [
                [{"document_id": _DOC_UUID, "chunk_index": 0}]
            ],
            "distances": [[0.2]],
        }
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_client_cls.return_value = mock_client

        store = ChromaStore(persist_directory="/tmp/test")
        store._hybrid_search_sync(
            query_embedding=[0.1], query_text="", k=3, collection_name="c"
        )
        call_kwargs = mock_collection.query.call_args[1]
        # When query_text is empty, query_texts should NOT be passed
        assert "query_texts" not in call_kwargs
        assert "query_embeddings" in call_kwargs

    @patch(
        "src.infrastructure.vector_store.chroma_store.chromadb.PersistentClient"
    )
    def test_chroma_hybrid_search_whitespace_only_falls_back(
        self, mock_client_cls
    ):
        """When query_text is whitespace only, falls back to dense."""
        from src.infrastructure.vector_store.chroma_store import ChromaStore

        mock_collection = MagicMock()
        mock_collection.count.return_value = 3
        mock_collection.query.return_value = {
            "ids": [[_UUID1]],
            "documents": [["d"]],
            "embeddings": [[[0.1]]],
            "metadatas": [
                [{"document_id": _DOC_UUID, "chunk_index": 0}]
            ],
            "distances": [[0.1]],
        }
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_client_cls.return_value = mock_client

        store = ChromaStore(persist_directory="/tmp/test")
        store._hybrid_search_sync(
            query_embedding=[0.1], query_text="   ", k=3, collection_name="c"
        )
        call_kwargs = mock_collection.query.call_args[1]
        assert "query_texts" not in call_kwargs

    @patch(
        "src.infrastructure.vector_store.chroma_store.chromadb.PersistentClient"
    )
    def test_chroma_hybrid_search_missing_collection_returns_empty(
        self, mock_client_cls
    ):
        """When collection doesn't exist (ValueError), return []."""
        from src.infrastructure.vector_store.chroma_store import ChromaStore

        mock_client = MagicMock()
        mock_client.get_collection.side_effect = ValueError("not found")
        mock_client_cls.return_value = mock_client

        store = ChromaStore(persist_directory="/tmp/test")
        result = store._hybrid_search_sync(
            query_embedding=[0.1], query_text="q", k=3, collection_name="c"
        )
        assert result == []

    @patch(
        "src.infrastructure.vector_store.chroma_store.chromadb.PersistentClient"
    )
    def test_chroma_hybrid_search_multiple_results(self, mock_client_cls):
        """hybrid_search returns multiple chunks with correct structure."""
        from src.infrastructure.vector_store.chroma_store import ChromaStore

        mock_collection = MagicMock()
        mock_collection.count.return_value = 10
        mock_collection.query.return_value = {
            "ids": [[_UUID1, _UUID2]],
            "documents": [["doc one", "doc two"]],
            "embeddings": [[[0.1, 0.2], [0.3, 0.4]]],
            "metadatas": [
                [
                    {"document_id": _DOC_UUID, "chunk_index": 0},
                    {"document_id": _DOC_UUID, "chunk_index": 1},
                ]
            ],
            "distances": [[0.2, 0.5]],
        }
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_client_cls.return_value = mock_client

        store = ChromaStore(persist_directory="/tmp/test")
        result = store._hybrid_search_sync(
            query_embedding=[0.1, 0.2],
            query_text="test query",
            k=5,
            collection_name="docs",
        )

        assert len(result) == 2
        assert result[0].content == "doc one"
        assert result[1].content == "doc two"
        # score = 1 - distance
        assert result[0].metadata["score"] == pytest.approx(0.8)
        assert result[1].metadata["score"] == pytest.approx(0.5)

    @patch(
        "src.infrastructure.vector_store.chroma_store.chromadb.PersistentClient"
    )
    def test_chroma_hybrid_search_empty_query_results(self, mock_client_cls):
        """hybrid_search returns [] when query returns no ids."""
        from src.infrastructure.vector_store.chroma_store import ChromaStore

        mock_collection = MagicMock()
        mock_collection.count.return_value = 5
        mock_collection.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "embeddings": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        mock_client_cls.return_value = mock_client

        store = ChromaStore(persist_directory="/tmp/test")
        result = store._hybrid_search_sync(
            query_embedding=[0.1], query_text="q", k=3, collection_name="c"
        )
        assert result == []

