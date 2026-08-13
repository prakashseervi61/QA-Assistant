"""Unit tests for the Qdrant vector store (mocked client — no live server).

The :class:`QdrantVectorStore` is exercised with a mocked ``QdrantClient``
and the real ``qdrant_client.http.models`` module is used to build the
expected filter/query payloads, so no Qdrant server is ever contacted.
"""

import builtins
import importlib
import logging
import sys
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from qdrant_client.http import models
from src.infrastructure.vector_store.vector_store_factory import (
    create_vector_store,
)

from src.domain.value_objects.chunk import Chunk
from src.infrastructure.vector_store.qdrant_store import QdrantVectorStore

COLLECTION = "documents"
EMBEDDING = [0.1, 0.2, 0.3]


@pytest.fixture
def store():
    """A QdrantVectorStore whose client is a MagicMock (no server I/O)."""
    with patch(
        "src.infrastructure.vector_store.qdrant_store.get_settings"
    ) as mock_settings:
        settings = MagicMock()
        settings.EMBEDDING_DIM = None
        mock_settings.return_value = settings

        instance = QdrantVectorStore(url="http://localhost:6333", api_key="")
        instance._client = MagicMock()
        instance._client.collection_exists.return_value = False
        yield instance


def make_point(
    content: str = "alpha",
    score: float = 0.9,
    embedding: list[float] | None = EMBEDDING,
    document_id: str | None = None,
    chunk_index: int = 0,
    **metadata,
) -> models.ScoredPoint:
    """Build a ScoredPoint with a flat payload like the store writes."""
    payload = {
        "content": content,
        "document_id": document_id or str(uuid4()),
        "chunk_index": chunk_index,
        **metadata,
    }
    return models.ScoredPoint(
        id=str(uuid4()),
        version=0,
        score=score,
        payload=payload,
        vector=embedding,
    )


class TestAddDocuments:
    @pytest.mark.asyncio
    async def test_add_documents_creates_collection_and_upserts(self, store):
        """Collection is created on demand and points carry payload metadata."""
        metadata_uuid = uuid4()
        chunks = [
            Chunk(
                content="alpha",
                embedding=EMBEDDING,
                metadata={"filename": "a.txt", "owner_id": metadata_uuid},
                chunk_index=0,
            ),
            Chunk(
                content="beta",
                embedding=[0.4, 0.5, 0.6],
                metadata={"filename": "b.txt"},
                chunk_index=1,
            ),
        ]

        await store.add_documents(chunks, COLLECTION)

        # Collection created on demand with the first chunk's dimension.
        store._client.create_collection.assert_called_once()
        create_kwargs = store._client.create_collection.call_args.kwargs
        assert create_kwargs["collection_name"] == COLLECTION
        assert create_kwargs["vectors_config"].size == len(EMBEDDING)
        assert create_kwargs["vectors_config"].distance == models.Distance.COSINE

        # Upserted with str() ids, embeddings, content, and serialized metadata.
        store._client.upsert.assert_called_once()
        points = store._client.upsert.call_args.kwargs["points"]
        assert len(points) == 2
        assert points[0].id == str(chunks[0].id)
        assert points[0].vector == EMBEDDING
        assert points[0].payload["content"] == "alpha"
        assert points[0].payload["document_id"] == str(chunks[0].document_id)
        assert points[0].payload["chunk_index"] == 0
        assert points[0].payload["filename"] == "a.txt"
        # UUID metadata values are stringified for JSON-serializable payloads.
        assert points[0].payload["owner_id"] == str(metadata_uuid)
        assert points[1].payload["content"] == "beta"

    @pytest.mark.asyncio
    async def test_add_documents_reuses_existing_collection(self, store):
        """An existing collection is reused, not recreated."""
        store._client.collection_exists.return_value = True

        await store.add_documents(
            [Chunk(content="alpha", embedding=EMBEDDING)], COLLECTION
        )

        store._client.create_collection.assert_not_called()
        store._client.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_documents_uses_configured_embedding_dim(self, store):
        """An EMBEDDING_DIM setting overrides the first chunk's length."""
        with patch(
            "src.infrastructure.vector_store.qdrant_store.get_settings"
        ) as mock_settings:
            settings = MagicMock()
            settings.EMBEDDING_DIM = 7
            mock_settings.return_value = settings

            await store.add_documents(
                [Chunk(content="alpha", embedding=EMBEDDING)], COLLECTION
            )

        create_kwargs = store._client.create_collection.call_args.kwargs
        assert create_kwargs["vectors_config"].size == 7

    @pytest.mark.asyncio
    async def test_add_documents_raises_value_error_without_embedding(self, store):
        """A chunk without an embedding is rejected (mirrors ChromaStore)."""
        with pytest.raises(ValueError, match="no embedding"):
            await store.add_documents([Chunk(content="alpha")], COLLECTION)
        store._client.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_documents_empty_list_is_a_noop(self, store):
        """Empty chunk lists are logged and skipped."""
        result = await store.add_documents([], COLLECTION)
        assert result is None
        store._client.create_collection.assert_not_called()
        store._client.upsert.assert_not_called()


class TestSimilaritySearch:
    @pytest.mark.asyncio
    async def test_similarity_search_returns_chunks_with_filter(self, store):
        """Results are Chunks with content/metadata and the filter is applied."""
        store._client.collection_exists.return_value = True
        document_id = str(uuid4())
        point = make_point(
            content="alpha",
            score=0.9,
            embedding=EMBEDDING,
            document_id=document_id,
            chunk_index=2,
            filename="a.txt",
        )
        store._client.query_points.return_value = models.QueryResponse(
            points=[point]
        )

        results = await store.similarity_search(
            EMBEDDING, 5, COLLECTION, {"filename": "a.txt"}
        )

        assert len(results) == 1
        chunk = results[0]
        assert chunk.content == "alpha"
        assert str(chunk.document_id) == document_id
        assert chunk.chunk_index == 2
        assert chunk.embedding == EMBEDDING
        assert chunk.metadata["filename"] == "a.txt"
        assert chunk.metadata["score"] == 0.9
        # Structural payload keys are not leaked into user metadata.
        assert "content" not in chunk.metadata
        assert "document_id" not in chunk.metadata

        query_kwargs = store._client.query_points.call_args.kwargs
        assert query_kwargs["query"] == EMBEDDING
        assert query_kwargs["limit"] == 5
        assert query_kwargs["query_filter"] == models.Filter(
            must=[
                models.FieldCondition(
                    key="filename", match=models.MatchValue(value="a.txt")
                )
            ]
        )

    @pytest.mark.asyncio
    async def test_similarity_search_missing_collection_returns_empty(self, store):
        """A collection that does not exist yields no results."""
        results = await store.similarity_search(EMBEDDING, 5, COLLECTION)
        assert results == []
        store._client.query_points.assert_not_called()


class TestHybridSearch:
    @pytest.mark.asyncio
    async def test_hybrid_search_uses_prefetch_and_rrf(self, store):
        """Installed clients use prefetch + Fusion.RRF with a must filter."""
        store._client.collection_exists.return_value = True
        point = make_point(content="alpha", score=0.81)
        store._client.query_points.return_value = models.QueryResponse(
            points=[point]
        )

        results = await store.hybrid_search(
            EMBEDDING,
            "keyword text",
            k=3,
            collection_name=COLLECTION,
            metadata_filter={"filename": "a.txt"},
        )

        assert len(results) == 1
        assert results[0].content == "alpha"
        assert results[0].metadata["score"] == 0.81

        call_kwargs = store._client.query_points.call_args.kwargs
        assert call_kwargs["collection_name"] == COLLECTION
        assert call_kwargs["limit"] == 3
        prefetch = call_kwargs["prefetch"]
        assert len(prefetch) == 2
        assert prefetch[0].query == EMBEDDING
        assert prefetch[1].query == "keyword text"
        assert call_kwargs["query"].fusion == models.Fusion.RRF
        assert call_kwargs["query_filter"] == models.Filter(
            must=[
                models.FieldCondition(
                    key="filename", match=models.MatchValue(value="a.txt")
                )
            ]
        )

    @pytest.mark.asyncio
    async def test_hybrid_search_manual_rrf_merge_fallback(
        self, store, monkeypatch
    ):
        """Clients without prefetch/fusion fall back to a manual RRF merge."""
        monkeypatch.setattr(
            QdrantVectorStore, "_supports_prefetch_fusion", lambda self: False
        )
        store._client.collection_exists.return_value = True
        document_id = str(uuid4())
        dense_hit = make_point(
            content="dense hit",
            score=0.9,
            embedding=EMBEDDING,
            document_id=document_id,
            chunk_index=0,
        )
        keyword_hit = make_point(
            content="keyword hit",
            score=0.7,
            embedding=[0.4, 0.5, 0.6],
            document_id=document_id,
            chunk_index=1,
        )
        # dense=[dense_hit], sparse=[dense_hit, keyword_hit] with k=60:
        # dense_hit -> 1/60 + 1/60, keyword_hit -> 1/61, so dense_hit wins.
        store._client.query_points.side_effect = [
            models.QueryResponse(points=[dense_hit]),
            models.QueryResponse(points=[dense_hit, keyword_hit]),
        ]

        results = await store.hybrid_search(
            EMBEDDING, "keyword", k=5, collection_name=COLLECTION
        )

        assert store._client.query_points.call_count == 2
        assert [r.content for r in results] == ["dense hit", "keyword hit"]
        assert results[0].metadata["score"] == round(2 / 60, 4)
        dense_call = store._client.query_points.call_args_list[0].kwargs
        sparse_call = store._client.query_points.call_args_list[1].kwargs
        assert dense_call["query"] == EMBEDDING
        assert sparse_call["query"] == "keyword"

    @pytest.mark.asyncio
    async def test_hybrid_search_empty_query_text_falls_back_to_dense(
        self, store
    ):
        """Whitespace-only query text falls back to pure dense search."""
        store._client.collection_exists.return_value = True
        point = make_point(content="alpha", score=0.9)
        store._client.query_points.return_value = models.QueryResponse(
            points=[point]
        )

        results = await store.hybrid_search(
            EMBEDDING, "   ", k=3, collection_name=COLLECTION
        )

        assert len(results) == 1
        call_kwargs = store._client.query_points.call_args.kwargs
        assert "prefetch" not in call_kwargs
        assert call_kwargs["query"] == EMBEDDING


class TestDeleteAndReads:
    @pytest.mark.asyncio
    async def test_delete_by_metadata_builds_filter(self, store):
        """Deletion targets a must-filter on the metadata key."""
        store._client.collection_exists.return_value = True
        document_id = str(uuid4())

        await store.delete_by_metadata({"document_id": document_id}, COLLECTION)

        delete_kwargs = store._client.delete.call_args.kwargs
        assert delete_kwargs["collection_name"] == COLLECTION
        assert delete_kwargs["points_selector"] == models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=document_id),
                )
            ]
        )

    @pytest.mark.asyncio
    async def test_delete_by_metadata_missing_collection_is_a_noop(self, store):
        """A missing collection means nothing to delete."""
        await store.delete_by_metadata({"document_id": str(uuid4())}, COLLECTION)
        store._client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_by_metadata_empty_filter_is_a_noop(self, store):
        """An empty filter is refused rather than deleting everything."""
        store._client.collection_exists.return_value = True
        await store.delete_by_metadata({}, COLLECTION)
        store._client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_collection_count(self, store):
        """The collection count is returned from Qdrant."""
        store._client.collection_exists.return_value = True
        store._client.count.return_value = models.CountResult(count=5)

        result = await store.get_collection_count(COLLECTION)

        assert result == 5
        store._client.count.assert_called_once_with(
            collection_name=COLLECTION, exact=True
        )

    @pytest.mark.asyncio
    async def test_get_collection_count_missing_collection_returns_zero(
        self, store
    ):
        """A missing collection counts as zero (mirrors ChromaStore)."""
        result = await store.get_collection_count(COLLECTION)
        assert result == 0
        store._client.count.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_documents_groups_by_document_id(self, store):
        """Chunks are grouped into one summary per document."""
        store._client.collection_exists.return_value = True
        document_id = str(uuid4())
        payload = {
            "document_id": document_id,
            "filename": "a.txt",
            "file_type": "txt",
            "file_size": 10,
            "created_at": "2024-01-01T00:00:00",
        }
        records = [
            models.Record(id=str(uuid4()), payload=dict(payload)),
            models.Record(id=str(uuid4()), payload=dict(payload)),
        ]
        store._client.scroll.return_value = (records, None)

        docs = await store.list_documents(COLLECTION)

        assert len(docs) == 1
        assert docs[0]["document_id"] == document_id
        assert docs[0]["filename"] == "a.txt"
        assert docs[0]["file_type"] == "txt"
        assert docs[0]["file_size"] == 10
        assert docs[0]["chunk_count"] == 2

    @pytest.mark.asyncio
    async def test_list_documents_missing_collection_returns_empty(self, store):
        """A missing collection yields no document summaries."""
        docs = await store.list_documents(COLLECTION)
        assert docs == []
        store._client.scroll.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_by_metadata_scrolls_with_filter(self, store):
        """Metadata lookups scroll with a must-filter on the payload."""
        store._client.collection_exists.return_value = True
        document_id = str(uuid4())
        record = models.Record(
            id=str(uuid4()),
            payload={
                "content": "alpha",
                "document_id": document_id,
                "chunk_index": 0,
                "content_hash": "abc123",
            },
            vector=EMBEDDING,
        )
        store._client.scroll.return_value = ([record], None)

        results = await store.get_by_metadata(
            {"content_hash": "abc123"}, COLLECTION
        )

        assert len(results) == 1
        assert results[0].content == "alpha"
        assert results[0].metadata["content_hash"] == "abc123"
        assert results[0].embedding == EMBEDDING
        scroll_kwargs = store._client.scroll.call_args.kwargs
        assert scroll_kwargs["scroll_filter"] == models.Filter(
            must=[
                models.FieldCondition(
                    key="content_hash", match=models.MatchValue(value="abc123")
                )
            ]
        )

    @pytest.mark.asyncio
    async def test_get_by_metadata_missing_collection_returns_empty(self, store):
        """A missing collection yields no metadata matches."""
        results = await store.get_by_metadata({"content_hash": "abc123"}, COLLECTION)
        assert results == []
        store._client.scroll.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_documents_by_ids_retrieves_records(self, store):
        """Chunks are retrieved by their point IDs."""
        store._client.collection_exists.return_value = True
        chunk_id = str(uuid4())
        record = models.Record(
            id=chunk_id,
            payload={
                "content": "alpha",
                "document_id": str(uuid4()),
                "chunk_index": 0,
            },
            vector=EMBEDDING,
        )
        store._client.retrieve.return_value = [record]

        results = await store.get_documents_by_ids([chunk_id], COLLECTION)

        assert len(results) == 1
        assert results[0].id == UUID(chunk_id)
        assert results[0].content == "alpha"
        assert results[0].embedding == EMBEDDING
        store._client.retrieve.assert_called_once_with(
            collection_name=COLLECTION,
            ids=[chunk_id],
            with_payload=True,
            with_vectors=True,
        )

    @pytest.mark.asyncio
    async def test_get_documents_by_ids_empty_returns_empty(self, store):
        """Empty ID lists short-circuit to an empty result."""
        results = await store.get_documents_by_ids([], COLLECTION)
        assert results == []
        store._client.retrieve.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_errors_become_runtime_error(self, store):
        """Connection/query failures surface as RuntimeError (not a crash)."""
        store._client.collection_exists.side_effect = ConnectionError(
            "server down"
        )

        with pytest.raises(RuntimeError, match="similarity search failed"):
            await store.similarity_search(EMBEDDING, 5, COLLECTION)


class TestVectorStoreFactory:
    def test_factory_returns_qdrant_when_configured(self):
        """VECTOR_STORE_BACKEND=qdrant -> QdrantVectorStore."""
        with (
            patch(
                "src.infrastructure.vector_store.vector_store_factory.get_settings"
            ) as mock_settings,
            patch(
                "src.infrastructure.vector_store.vector_store_factory.QdrantVectorStore"
            ) as mock_qdrant,
        ):
            settings = MagicMock()
            settings.VECTOR_STORE_BACKEND = "qdrant"
            settings.QDRANT_URL = "http://localhost:6333"
            settings.QDRANT_API_KEY = ""
            mock_settings.return_value = settings

            store = create_vector_store()

            mock_qdrant.assert_called_once_with(
                url="http://localhost:6333", api_key=""
            )
            assert store is mock_qdrant.return_value

    def test_factory_returns_chroma_by_default(self):
        """VECTOR_STORE_BACKEND=chroma (the default) -> ChromaStore."""
        with (
            patch(
                "src.infrastructure.vector_store.vector_store_factory.get_settings"
            ) as mock_settings,
            patch(
                "src.infrastructure.vector_store.vector_store_factory.ChromaStore"
            ) as mock_chroma,
        ):
            settings = MagicMock()
            settings.VECTOR_STORE_BACKEND = "chroma"
            settings.CHROMA_PERSIST_DIR = "./data/chroma"
            mock_settings.return_value = settings

            store = create_vector_store()

            mock_chroma.assert_called_once_with(persist_directory="./data/chroma")
            assert store is mock_chroma.return_value

    def test_factory_warns_and_falls_back_to_chroma_for_invalid_backend(
        self, caplog
    ):
        """Unknown backends warn and fall back to ChromaStore."""
        with (
            patch(
                "src.infrastructure.vector_store.vector_store_factory.get_settings"
            ) as mock_settings,
            patch(
                "src.infrastructure.vector_store.vector_store_factory.ChromaStore"
            ) as mock_chroma,
        ):
            settings = MagicMock()
            settings.VECTOR_STORE_BACKEND = "elastic"
            mock_settings.return_value = settings

            with caplog.at_level(logging.WARNING):
                store = create_vector_store()

            assert store is mock_chroma.return_value

        assert "VECTOR_STORE_BACKEND" in caplog.text
        assert "chroma" in caplog.text.lower()

    def test_factory_falls_back_to_chroma_when_qdrant_unavailable(self):
        """Qdrant construction failure -> ChromaStore fallback, no crash."""
        with (
            patch(
                "src.infrastructure.vector_store.vector_store_factory.get_settings"
            ) as mock_settings,
            patch(
                "src.infrastructure.vector_store.vector_store_factory.QdrantVectorStore",
                side_effect=RuntimeError("no qdrant-client"),
            ),
            patch(
                "src.infrastructure.vector_store.vector_store_factory.ChromaStore"
            ) as mock_chroma,
        ):
            settings = MagicMock()
            settings.VECTOR_STORE_BACKEND = "qdrant"
            settings.QDRANT_URL = "http://localhost:6333"
            settings.QDRANT_API_KEY = ""
            mock_settings.return_value = settings

            store = create_vector_store()

            assert store is mock_chroma.return_value


class TestLazyQdrantImport:
    """The qdrant_client package is optional and imported lazily."""

    def _block_qdrant_client(self, monkeypatch):
        real_import = builtins.__import__

        def _blocked(name, *args, **kwargs):
            if name.startswith("qdrant_client"):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _blocked)

    def test_module_imports_without_qdrant_client(self, monkeypatch):
        """Importing the module must not require qdrant-client."""
        self._block_qdrant_client(monkeypatch)
        monkeypatch.delitem(
            sys.modules,
            "src.infrastructure.vector_store.qdrant_store",
            raising=False,
        )

        module = importlib.import_module("src.infrastructure.vector_store.qdrant_store")

        assert hasattr(module, "QdrantVectorStore")

    def test_instantiation_fails_clearly_without_qdrant_client(self, monkeypatch):
        """Instantiating without qdrant-client raises a clear RuntimeError."""
        self._block_qdrant_client(monkeypatch)

        with pytest.raises(RuntimeError, match="qdrant-client"):
            QdrantVectorStore(url="http://localhost:6333")
