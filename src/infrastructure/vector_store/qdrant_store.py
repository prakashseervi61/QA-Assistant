"""Qdrant vector store implementation (optional dependency).

:class:`QdrantVectorStore` is a drop-in alternative to
:class:`~src.infrastructure.vector_store.chroma_store.ChromaStore`
selected via the ``VECTOR_STORE_BACKEND`` setting (see
``vector_store_factory.py``). The ``qdrant-client`` package is an
optional dependency (``pip install -e ".[qdrant]"``) and is imported
lazily so the rest of the application runs fine without it installed.
"""

import asyncio
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from src.domain.interfaces.vector_store import VectorStore
from src.domain.value_objects.chunk import Chunk
from src.infrastructure.config.settings import get_settings

if TYPE_CHECKING:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qdrant_models

logger = logging.getLogger(__name__)

# Max points fetched per scroll request. Qdrant caps a single scroll page
# at 256 points; the scroll loops page through until exhausted.
_SCROLL_BATCH_SIZE = 256

# Reciprocal Rank Fusion constant used by the manual RRF fallback. Qdrant's
# own ``Fusion.RRF`` uses the same k=60 convention.
_RRF_K = 60


class QdrantVectorStore(VectorStore):
    """Vector store implementation backed by a Qdrant server.

    Collections are created on demand with cosine distance. The vector
    dimensionality is fixed when a collection is created (Qdrant cannot
    change it afterwards): it is taken from the ``EMBEDDING_DIM`` setting
    when present, otherwise from the first chunk's embedding length — every
    chunk stored in a collection must therefore share the same embedding
    size.

    All Qdrant operations are synchronous, so they are executed in a
    thread pool via :func:`asyncio.to_thread` to satisfy the async
    interface contract.

    Args:
        url: Qdrant server URL (default ``http://localhost:6333``).
        api_key: Optional API key for a secured Qdrant deployment.
    """

    def __init__(self, url: str = "http://localhost:6333", api_key: str = "") -> None:
        try:
            import qdrant_client
            from qdrant_client.http import models
        except ImportError as exc:
            raise RuntimeError(
                "QdrantVectorStore requires the optional 'qdrant-client' "
                "package; install it with: pip install -e '.[qdrant]'"
            ) from exc
        # An empty api_key is treated as "no auth" so the client does not
        # warn about credentials over an insecure connection.
        if api_key:
            self._client: QdrantClient = qdrant_client.QdrantClient(
                url=url, api_key=api_key
            )
        else:
            self._client = qdrant_client.QdrantClient(url=url)
        self._models = models

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_metadata(chunk: Chunk) -> dict[str, object]:
        """Convert a chunk's metadata into JSON-serializable values.

        Mirrors ChromaStore's convention: ``bool``/``int``/``float``/``str``
        pass through, ``bytes`` become hex, ``None`` values are dropped, and
        everything else (notably ``UUID``) is stringified so Qdrant payloads
        stay JSON-safe.
        """
        serialized: dict[str, object] = {}
        for key, value in chunk.metadata.items():
            if value is None:
                continue
            if isinstance(value, bool | int | float | str):
                serialized[key] = value
            elif isinstance(value, bytes):
                serialized[key] = value.hex()
            else:
                serialized[key] = str(value)
        return serialized

    def _build_payload(self, chunk: Chunk) -> dict[str, object]:
        """Build the Qdrant point payload for a chunk.

        The content text plus ``document_id``/``chunk_index`` and the
        user-supplied metadata all live flat in the payload so metadata
        filters can target top-level payload keys.
        """
        payload: dict[str, object] = {
            "content": chunk.content,
            "document_id": str(chunk.document_id),
            "chunk_index": chunk.chunk_index,
        }
        payload.update(self._serialize_metadata(chunk))
        return payload

    def _collection_dimension(self, chunk: Chunk) -> int:
        """Resolve the vector dimensionality for a new collection.

        Uses the ``EMBEDDING_DIM`` setting when present; otherwise the
        first chunk's embedding length. Qdrant fixes the dimension at
        collection creation time, so all chunks in a collection must use
        the same embedding size.
        """
        settings = get_settings()
        configured = getattr(settings, "EMBEDDING_DIM", None)
        if configured is not None:
            return int(configured)
        return len(chunk.embedding or [])

    def _build_filter(
        self, metadata_filter: dict[str, object] | None
    ) -> qdrant_models.Filter | None:
        """Convert a flat metadata dict into a Qdrant ``must`` filter.

        Each key/value pair becomes a :class:`FieldCondition` against the
        matching top-level payload key. List values become ``MatchAny``.
        """
        if not metadata_filter:
            return None
        models = self._models
        conditions: list[qdrant_models.Condition] = []
        for key, value in metadata_filter.items():
            if isinstance(value, list):
                conditions.append(
                    models.FieldCondition(
                        key=str(key),
                        match=models.MatchAny(any=value),
                    )
                )
            elif isinstance(value, bool | int | str):
                conditions.append(
                    models.FieldCondition(
                        key=str(key),
                        match=models.MatchValue(value=value),
                    )
                )
            else:
                # Qdrant's MatchValue type is bool|int|str; anything else
                # (floats, datetimes, ...) is stringified.
                conditions.append(
                    models.FieldCondition(
                        key=str(key),
                        match=models.MatchValue(value=str(value)),
                    )
                )
        return models.Filter(must=conditions)

    def _get_or_create_collection(self, collection_name: str, dimension: int) -> None:
        """Create the collection when it does not exist yet."""
        if not self._client.collection_exists(collection_name):
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=self._models.VectorParams(
                    size=dimension,
                    distance=self._models.Distance.COSINE,
                ),
            )
            logger.info(
                "Created Qdrant collection '%s' (dimension %d)",
                collection_name,
                dimension,
            )

    def _records_to_chunks(
        self,
        records: Sequence[qdrant_models.ScoredPoint | qdrant_models.Record],
        score_key: str | None = None,
    ) -> list[Chunk]:
        """Convert Qdrant records/points into :class:`Chunk` instances.

        The ``content``/``document_id``/``chunk_index`` payload keys become
        Chunk fields; everything else in the payload (plus the score, when
        requested) becomes chunk metadata — mirroring ChromaStore's return
        shape.
        """
        chunks: list[Chunk] = []
        for record in records:
            payload = dict(record.payload or {})
            document_id_str = payload.pop("document_id", None)
            chunk_index = int(payload.pop("chunk_index", 0))
            score = getattr(record, score_key, None) if score_key else None
            if score is not None:
                payload["score"] = round(float(score), 4)
            vector = record.vector
            embedding = (
                [float(v) for v in vector if isinstance(v, int | float)]
                if isinstance(vector, list)
                else None
            )
            chunks.append(
                Chunk(
                    id=UUID(str(record.id)),
                    # Chunk.document_id is UUID (non-optional), mirroring
                    # ChromaStore; payloads may omit it.
                    document_id=UUID(document_id_str) if document_id_str else None,  # type: ignore[arg-type]
                    content=str(payload.pop("content", "")),
                    embedding=embedding,
                    metadata=payload,
                    chunk_index=chunk_index,
                )
            )
        return chunks

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def add_documents(self, chunks: list[Chunk], collection_name: str) -> None:
        """Store text chunks with their embeddings.

        Args:
            chunks: List of ``Chunk`` instances to persist.
            collection_name: Name of the Qdrant collection.

        Raises:
            ValueError: If a chunk has no embedding.
            RuntimeError: If the Qdrant upsert fails.
        """
        if not chunks:
            logger.warning("add_documents called with empty chunk list")
            return

        def _upsert() -> None:
            self._get_or_create_collection(
                collection_name, self._collection_dimension(chunks[0])
            )

            points: list[qdrant_models.PointStruct] = []
            for chunk in chunks:
                if chunk.embedding is None:
                    raise ValueError(
                        f"Chunk {chunk.id} has no embedding — "
                        "embeddings must be generated before storing."
                    )
                points.append(
                    self._models.PointStruct(
                        id=str(chunk.id),
                        vector=chunk.embedding,
                        payload=self._build_payload(chunk),
                    )
                )

            self._client.upsert(
                collection_name=collection_name,
                points=points,
                wait=True,
            )
            logger.info(
                "Upserted %d chunks into collection '%s'",
                len(points),
                collection_name,
            )

        try:
            await asyncio.to_thread(_upsert)
        except ValueError:
            raise
        except Exception as exc:
            logger.error("Qdrant add_documents failed: %s", exc)
            raise RuntimeError(f"Qdrant upsert failed: {exc}") from exc

    async def similarity_search(
        self,
        query_embedding: list[float],
        k: int,
        collection_name: str,
        metadata_filter: dict[str, object] | None = None,
    ) -> list[Chunk]:
        """Retrieve the *k* most similar chunks to the query embedding.

        Uses cosine similarity (the collection's configured distance) with
        an optional ``must`` metadata filter. Returns an empty list when
        the collection does not exist.

        Args:
            query_embedding: The query vector.
            k: Number of results to return.
            collection_name: Name of the Qdrant collection.
            metadata_filter: Optional metadata filter dict applied as a
                ``must`` condition (e.g. ``{"document_id": "abc"}``).

        Returns:
            A list of ``Chunk`` instances ordered by relevance (most
            similar first). Empty list if the collection does not exist.

        Raises:
            RuntimeError: If the Qdrant query fails.
        """
        try:
            return await asyncio.to_thread(
                self._query_sync,
                query_embedding,
                k,
                collection_name,
                metadata_filter,
            )
        except Exception as exc:
            logger.error("Qdrant similarity search failed: %s", exc)
            raise RuntimeError(f"Qdrant similarity search failed: {exc}") from exc

    def _query_sync(
        self,
        query_embedding: list[float],
        k: int,
        collection_name: str,
        metadata_filter: dict[str, object] | None = None,
    ) -> list[Chunk]:
        """Synchronous similarity search implementation."""
        if not self._client.collection_exists(collection_name):
            return []

        response = self._client.query_points(
            collection_name=collection_name,
            query=query_embedding,
            query_filter=self._build_filter(metadata_filter),
            limit=k,
            with_payload=True,
            with_vectors=True,
        )
        chunks = self._records_to_chunks(response.points, score_key="score")
        logger.debug(
            "similarity_search returned %d chunks from '%s'",
            len(chunks),
            collection_name,
        )
        return chunks

    # ------------------------------------------------------------------
    # Hybrid search
    # ------------------------------------------------------------------

    async def hybrid_search(
        self,
        query_embedding: list[float],
        query_text: str,
        k: int = 5,
        collection_name: str = "documents",
        metadata_filter: dict[str, object] | None = None,
    ) -> list[Chunk]:
        """Hybrid search combining dense vectors and keyword matching.

        Uses Qdrant's ``prefetch`` + ``Fusion.RRF`` when the installed
        client exposes those APIs (the preferred path): one dense prefetch
        for *query_embedding* and one text prefetch for *query_text* are
        fused with reciprocal rank fusion. When the client is too old to
        support prefetch/fusion, falls back to a manual RRF merge of two
        separate dense and text queries.

        Falls back to pure dense :meth:`similarity_search` when
        *query_text* is empty or whitespace-only (mirroring ChromaStore).

        Note: the keyword leg of the query requires the collection to
        support text search (a sparse-vector or full-text index). The
        current schema stores dense vectors only, so on a live server the
        keyword leg is best-effort and any server rejection surfaces as a
        :class:`RuntimeError` like every other query failure.
        """
        if not query_text or not query_text.strip():
            return await self.similarity_search(
                query_embedding, k, collection_name, metadata_filter
            )

        try:
            return await asyncio.to_thread(
                self._hybrid_search_sync,
                query_embedding,
                query_text,
                k,
                collection_name,
                metadata_filter,
            )
        except Exception as exc:
            logger.error("Qdrant hybrid search failed: %s", exc)
            raise RuntimeError(f"Qdrant hybrid search failed: {exc}") from exc

    def _hybrid_search_sync(
        self,
        query_embedding: list[float],
        query_text: str,
        k: int,
        collection_name: str,
        metadata_filter: dict[str, object] | None = None,
    ) -> list[Chunk]:
        """Synchronous hybrid search implementation."""
        if not self._client.collection_exists(collection_name):
            return []
        if self._supports_prefetch_fusion():
            return self._prefetch_fusion_search(
                query_embedding, query_text, k, collection_name, metadata_filter
            )
        return self._manual_rrf_search(
            query_embedding, query_text, k, collection_name, metadata_filter
        )

    def _supports_prefetch_fusion(self) -> bool:
        """True when the installed qdrant-client exposes prefetch + Fusion.RRF.

        Prefetch/fusion was introduced in newer qdrant-client releases;
        older clients fall back to a manual RRF merge of dense and text
        results.
        """
        models = self._models
        return (
            hasattr(models, "Prefetch")
            and hasattr(models, "Fusion")
            and hasattr(models, "FusionQuery")
        )

    def _prefetch_fusion_search(
        self,
        query_embedding: list[float],
        query_text: str,
        k: int,
        collection_name: str,
        metadata_filter: dict[str, object] | None,
    ) -> list[Chunk]:
        """Hybrid search via Qdrant prefetch + ``Fusion.RRF``."""
        models = self._models
        prefetch_limit = k * 2
        response = self._client.query_points(
            collection_name=collection_name,
            prefetch=[
                models.Prefetch(query=query_embedding, limit=prefetch_limit),
                models.Prefetch(query=query_text, limit=prefetch_limit),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=self._build_filter(metadata_filter),
            limit=k,
            with_payload=True,
            with_vectors=True,
        )
        chunks = self._records_to_chunks(response.points, score_key="score")
        logger.debug(
            "hybrid_search (prefetch+RRF) returned %d chunks from '%s'",
            len(chunks),
            collection_name,
        )
        return chunks

    def _manual_rrf_search(
        self,
        query_embedding: list[float],
        query_text: str,
        k: int,
        collection_name: str,
        metadata_filter: dict[str, object] | None,
    ) -> list[Chunk]:
        """Hybrid search via two queries merged with manual Reciprocal Rank Fusion."""
        query_filter = self._build_filter(metadata_filter)
        dense_response = self._client.query_points(
            collection_name=collection_name,
            query=query_embedding,
            query_filter=query_filter,
            limit=k * 2,
            with_payload=True,
            with_vectors=True,
        )
        sparse_response = self._client.query_points(
            collection_name=collection_name,
            query=query_text,
            query_filter=query_filter,
            limit=k * 2,
            with_payload=True,
            with_vectors=True,
        )
        chunks = self._merge_rrf(dense_response.points, sparse_response.points, k)
        logger.debug(
            "hybrid_search (manual RRF) returned %d chunks from '%s'",
            len(chunks),
            collection_name,
        )
        return chunks

    def _merge_rrf(
        self,
        dense_points: list[qdrant_models.ScoredPoint],
        sparse_points: list[qdrant_models.ScoredPoint],
        k: int,
    ) -> list[Chunk]:
        """Manually merge dense and sparse results with Reciprocal Rank Fusion.

        Each result list contributes ``1 / (rank + _RRF_K)`` (k=60, the same
        constant Qdrant's ``Fusion.RRF`` uses). Points appearing in both
        lists accumulate score; the top-*k* are returned in score order with
        the fused score stored in ``metadata["score"]``.
        """
        combined: dict[str, qdrant_models.ScoredPoint] = {}
        rrf_scores: dict[str, float] = {}

        for points in (dense_points, sparse_points):
            for rank, point in enumerate(points):
                point_id = str(point.id)
                rrf_scores[point_id] = rrf_scores.get(point_id, 0.0) + 1.0 / (
                    rank + _RRF_K
                )
                combined[point_id] = point

        ranked_ids = sorted(
            rrf_scores, key=lambda point_id: rrf_scores[point_id], reverse=True
        )[:k]

        chunks = self._records_to_chunks([combined[i] for i in ranked_ids])
        for chunk in chunks:
            chunk.metadata["score"] = round(rrf_scores[str(chunk.id)], 4)
        return chunks

    # ------------------------------------------------------------------
    # Deletion / reads
    # ------------------------------------------------------------------

    async def delete_by_metadata(self, filter_dict: dict, collection_name: str) -> None:
        """Delete chunks whose metadata matches all entries in *filter_dict*.

        Args:
            filter_dict: Metadata key-value pairs to match.
            collection_name: Name of the Qdrant collection.

        Raises:
            RuntimeError: If the deletion fails.
        """
        if not filter_dict:
            logger.warning(
                "delete_by_metadata called with an empty filter — refusing to "
                "delete the whole collection '%s'",
                collection_name,
            )
            return

        def _delete() -> None:
            if not self._client.collection_exists(collection_name):
                logger.debug(
                    "Collection '%s' does not exist — nothing to delete",
                    collection_name,
                )
                return
            selector = self._build_filter(filter_dict)
            assert selector is not None, "empty filter is handled above"
            self._client.delete(
                collection_name=collection_name,
                points_selector=selector,
                wait=True,
            )
            logger.info(
                "Deleted chunks matching %s from collection '%s'",
                filter_dict,
                collection_name,
            )

        try:
            await asyncio.to_thread(_delete)
        except Exception as exc:
            logger.error("Qdrant delete_by_metadata failed: %s", exc)
            raise RuntimeError(f"Qdrant delete failed: {exc}") from exc

    async def get_collection_count(self, collection_name: str) -> int:
        """Return the number of chunks in a collection.

        Returns ``0`` when the collection does not exist.

        Raises:
            RuntimeError: If the count query fails.
        """

        def _count() -> int:
            if not self._client.collection_exists(collection_name):
                return 0
            result = self._client.count(
                collection_name=collection_name, exact=True
            )
            return int(result.count)

        try:
            return await asyncio.to_thread(_count)
        except Exception as exc:
            logger.error("Qdrant get_collection_count failed: %s", exc)
            raise RuntimeError(f"Qdrant count query failed: {exc}") from exc

    async def list_documents(self, collection_name: str) -> list[dict]:
        """Return a summary per ingested document in the collection.

        Mirrors :meth:`ChromaStore.list_documents`: scrolls all points and
        groups them by their ``document_id`` payload field, returning one
        entry per document with its filename, size, chunk count, and
        creation timestamp.

        Args:
            collection_name: Name of the Qdrant collection.

        Returns:
            A list of dicts with keys: ``document_id``, ``filename``,
            ``file_type``, ``file_size``, ``chunk_count``, ``created_at``.
            Empty list if the collection does not exist.

        Raises:
            RuntimeError: If listing the documents fails.
        """

        def _list() -> list[dict]:
            if not self._client.collection_exists(collection_name):
                return []
            documents: dict[str, dict[str, object]] = {}
            chunk_counts: dict[str, int] = {}
            points, next_offset = self._client.scroll(
                collection_name=collection_name,
                limit=_SCROLL_BATCH_SIZE,
                with_payload=True,
                with_vectors=False,
            )
            while True:
                for point in points:
                    payload = point.payload or {}
                    document_id = payload.get("document_id")
                    if not document_id:
                        continue
                    doc_id = str(document_id)
                    chunk_counts[doc_id] = chunk_counts.get(doc_id, 0) + 1
                    if doc_id not in documents:
                        documents[doc_id] = {
                            "document_id": doc_id,
                            "filename": str(payload.get("filename", "unknown")),
                            "file_type": str(payload.get("file_type", "")),
                            "file_size": int(payload.get("file_size", 0) or 0),
                            "chunk_count": 0,
                            "created_at": str(payload.get("created_at", "")),
                        }
                if next_offset is None:
                    break
                points, next_offset = self._client.scroll(
                    collection_name=collection_name,
                    limit=_SCROLL_BATCH_SIZE,
                    offset=next_offset,
                    with_payload=True,
                    with_vectors=False,
                )
            for doc_id, count in chunk_counts.items():
                documents[doc_id]["chunk_count"] = count
            return list(documents.values())

        try:
            return await asyncio.to_thread(_list)
        except Exception as exc:
            logger.error("Qdrant list_documents failed: %s", exc)
            raise RuntimeError(f"Qdrant list_documents failed: {exc}") from exc

    async def get_documents_by_ids(
        self,
        ids: list[str],
        collection_name: str = "documents",
    ) -> list[Chunk]:
        """Retrieve chunks by their IDs from Qdrant.

        Args:
            ids: List of chunk ID strings to retrieve.
            collection_name: Name of the Qdrant collection.

        Returns:
            A list of ``Chunk`` instances for the found IDs. Missing IDs
            are silently skipped.
        """

        def _get() -> list[Chunk]:
            if not ids:
                return []
            if not self._client.collection_exists(collection_name):
                return []
            records = self._client.retrieve(
                collection_name=collection_name,
                ids=ids,
                with_payload=True,
                with_vectors=True,
            )
            return self._records_to_chunks(records)

        try:
            return await asyncio.to_thread(_get)
        except Exception as exc:
            logger.error("Qdrant get_documents_by_ids failed: %s", exc)
            raise RuntimeError(f"Qdrant get_documents_by_ids failed: {exc}") from exc

    async def get_by_metadata(
        self,
        metadata_filter: dict[str, object],
        collection_name: str = "documents",
    ) -> list[Chunk]:
        """Retrieve chunks whose metadata matches all entries in *metadata_filter*.

        Used by incremental ingestion to find existing chunks with a given
        ``content_hash``. The filter is applied server-side as a ``must``
        condition while scrolling the collection.

        Args:
            metadata_filter: Metadata key-value pairs to match.
            collection_name: Name of the Qdrant collection.

        Returns:
            A list of ``Chunk`` instances matching the filter. Empty list
            if the collection does not exist or has no matches.

        Raises:
            RuntimeError: If the scroll fails.
        """

        def _get() -> list[Chunk]:
            if not self._client.collection_exists(collection_name):
                return []
            scroll_filter = self._build_filter(metadata_filter)
            points, next_offset = self._client.scroll(
                collection_name=collection_name,
                scroll_filter=scroll_filter,
                limit=_SCROLL_BATCH_SIZE,
                with_payload=True,
                with_vectors=True,
            )
            chunks = self._records_to_chunks(points)
            while next_offset is not None:
                more, next_offset = self._client.scroll(
                    collection_name=collection_name,
                    scroll_filter=scroll_filter,
                    limit=_SCROLL_BATCH_SIZE,
                    offset=next_offset,
                    with_payload=True,
                    with_vectors=True,
                )
                chunks.extend(self._records_to_chunks(more))
            return chunks

        try:
            return await asyncio.to_thread(_get)
        except Exception as exc:
            logger.error("Qdrant get_by_metadata failed: %s", exc)
            raise RuntimeError(f"Qdrant get_by_metadata failed: {exc}") from exc
