import asyncio
import logging
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import NotFoundError

from src.domain.interfaces.vector_store import VectorStore
from src.domain.value_objects.chunk import Chunk

logger = logging.getLogger(__name__)

# Upper bound on rows per upsert. ChromaDB's own limit is read from the
# collection at runtime (it changes with the index config); this is only the
# cap we clamp to, so a future larger limit is picked up without a code change.
_DEFAULT_BATCH_SIZE = 5_000

# Used only when the collection will not report its limit. Well under the 5461
# that the default HNSW config allows.
_FALLBACK_BATCH_SIZE = 1_000


class ChromaStore(VectorStore):
    """Vector store implementation using ChromaDB.

    Uses a persistent ChromaDB client backed by the local filesystem.
    All ChromaDB operations are synchronous, so they are executed in a
    thread pool via :func:`asyncio.to_thread` to satisfy the async
    interface contract.

    Args:
        persist_directory: Filesystem path where ChromaDB persists data.
    """

    def __init__(self, persist_directory: str) -> None:
        self._persist_directory = persist_directory
        self._client = chromadb.PersistentClient(
            path=persist_directory,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_metadata(chunk: Chunk) -> dict[str, Any]:
        """Convert a chunk's metadata dict into ChromaDB-compatible values.

        ChromaDB only accepts ``str``, ``int``, ``float``, and ``bool``
        metadata values.  This helper:
        * Converts ``UUID`` instances to ``str``.
        * Drops keys whose value is ``None``.
        * Converts all other types to ``str`` as a safe fallback.
        """
        serialized: dict[str, Any] = {}
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

    @staticmethod
    def _build_chroma_metadata(chunk: Chunk) -> dict[str, Any]:
        """Build the full metadata dict stored alongside a chunk.

        Includes the ``document_id`` and ``chunk_index`` fields from the
        chunk value object itself, in addition to any user-supplied
        metadata.
        """
        base: dict[str, Any] = {
            "document_id": str(chunk.document_id),
            "chunk_index": chunk.chunk_index,
        }
        base.update(ChromaStore._serialize_metadata(chunk))
        return base

    def _get_or_create_collection(self, collection_name: str) -> chromadb.Collection:
        """Return an existing collection or create one with cosine distance."""
        return self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def add_documents(self, chunks: list[Chunk], collection_name: str) -> None:
        """Store text chunks with their embeddings.

        Args:
            chunks: List of ``Chunk`` instances to persist.
            collection_name: Name of the ChromaDB collection.

        Raises:
            ValueError: If *chunks* is empty or a chunk has no embedding.
            RuntimeError: If the ChromaDB upsert fails.
        """
        if not chunks:
            logger.warning("add_documents called with empty chunk list")
            return

        for chunk in chunks:
            if chunk.embedding is None:
                raise ValueError(
                    f"Chunk {chunk.id} has no embedding — "
                    "embeddings must be generated before storing."
                )

        # ChromaDB caps how many rows one upsert may carry (5461 on the default
        # HNSW config), and raises ValueError above that rather than splitting
        # the work itself. A single document large enough to exceed it — a few
        # hundred pages of text — therefore failed outright with an opaque 500
        # *after* the minutes spent parsing and embedding it. Batch instead.
        #
        # The cap is derived from the collection rather than hard-coded because
        # it moves with the index configuration; `max_batch_size` is the same
        # number ChromaDB validates against, so reading it back keeps the two
        # in step.
        collection = self._get_or_create_collection(collection_name)
        try:
            max_batch = int(collection.max_batch_size)
        except (
            Exception
        ):  # pragma: no cover - defensive: fall back to a known-safe size
            logger.warning(
                "Could not read max_batch_size from collection '%s'; using %d",
                collection_name,
                _FALLBACK_BATCH_SIZE,
            )
            max_batch = _FALLBACK_BATCH_SIZE

        # One row of slack under the cap: a batch exactly at the limit has
        # passed validation in some ChromaDB versions and failed in others once
        # metadata is expanded.
        batch_size = max(1, min(max_batch - 1, _DEFAULT_BATCH_SIZE))

        def _upsert() -> None:
            total = 0
            for start in range(0, len(chunks), batch_size):
                batch = chunks[start : start + batch_size]
                collection.upsert(
                    ids=[str(chunk.id) for chunk in batch],
                    documents=[chunk.content for chunk in batch],
                    embeddings=[chunk.embedding for chunk in batch],
                    metadatas=[self._build_chroma_metadata(chunk) for chunk in batch],
                )
                total += len(batch)
                logger.info(
                    "Upserted %d/%d chunks into collection '%s'",
                    total,
                    len(chunks),
                    collection_name,
                )

        try:
            await asyncio.to_thread(_upsert)
        except ValueError:
            raise
        except Exception as exc:
            logger.error("Failed to add documents to ChromaDB: %s", exc)
            raise RuntimeError(f"ChromaDB upsert failed: {exc}") from exc

    async def similarity_search(
        self,
        query_embedding: list[float],
        k: int,
        collection_name: str,
        metadata_filter: dict[str, object] | None = None,
    ) -> list[Chunk]:
        """Retrieve the *k* most similar chunks to the query embedding.

        Uses cosine similarity (the collection's configured distance).

        Args:
            query_embedding: The query vector.
            k: Number of results to return.
            collection_name: Name of the ChromaDB collection.
            metadata_filter: Optional metadata filter dict passed as
                ``where`` to ChromaDB (e.g. ``{"document_id": "abc"}``).

        Returns:
            A list of ``Chunk`` instances ordered by relevance
            (most similar first).  Empty list if the collection does
            not exist or contains no documents.

        Raises:
            RuntimeError: If the ChromaDB query fails.
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
            logger.error("ChromaDB similarity search failed: %s", exc)
            raise RuntimeError(f"ChromaDB similarity search failed: {exc}") from exc

    def _query_sync(
        self,
        query_embedding: list[float],
        k: int,
        collection_name: str,
        metadata_filter: dict[str, object] | None = None,
        query_text: str | None = None,
    ) -> list[Chunk]:
        """Synchronous search implementation, dense-only or hybrid.

        Args:
            query_embedding: The query vector.
            k: Number of results to return.
            collection_name: Name of the ChromaDB collection.
            metadata_filter: Optional metadata filter dict passed as
                ``where`` to ChromaDB.
            query_text: When given (and non-blank), also passed to ChromaDB as
                ``query_texts`` so it blends dense similarity with BM25-style
                keyword matching. Omit it for pure vector search.

        Returns:
            A list of ``Chunk`` instances ordered by relevance.

        ponytail: hybrid search was a second 92-line copy of this method whose
        only difference was one ``query_texts`` kwarg. Merged rather than
        parameterised separately.
        """
        try:
            collection = self._client.get_collection(collection_name)
        except (ValueError, NotFoundError):
            return []

        if collection.count() == 0:
            return []

        query_kwargs: dict[str, object] = {
            "query_embeddings": [query_embedding],
            "n_results": min(k, collection.count()),
            "include": [
                "documents",
                "embeddings",
                "metadatas",
                "distances",
            ],
        }
        if query_text and query_text.strip():
            query_kwargs["query_texts"] = [query_text]
        if metadata_filter:
            query_kwargs["where"] = metadata_filter

        results = collection.query(**query_kwargs)

        chunks: list[Chunk] = []
        if not results or not results.get("ids"):
            return chunks

        ids = results["ids"][0]
        documents = results.get("documents", [[]])[0]
        embeddings = results.get("embeddings", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        num_ids = len(ids)

        for idx in range(num_ids):
            metadata = dict(metadatas[idx]) if len(metadatas) > idx else {}
            document_id_str = metadata.pop("document_id", None)
            chunk_index = int(metadata.pop("chunk_index", 0))

            # Convert cosine distance to similarity score
            if len(distances) > idx:
                metadata["score"] = round(1.0 - float(distances[idx]), 4)

            from uuid import UUID

            embedding_list = list(embeddings[idx]) if len(embeddings) > idx else None

            chunk = Chunk(
                id=UUID(ids[idx]),
                document_id=UUID(document_id_str)  # type: ignore[arg-type]
                if document_id_str
                else None,
                content=documents[idx] if len(documents) > idx else "",
                embedding=embedding_list,
                metadata=metadata,
                chunk_index=chunk_index,
            )
            chunks.append(chunk)

        logger.debug(
            "query returned %d chunks from '%s' (hybrid=%s)",
            len(chunks),
            collection_name,
            bool(query_text),
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
        """Hybrid search combining dense and keyword retrieval via ChromaDB.

        When *query_text* is non-empty, passes both ``query_embeddings``
        and ``query_texts`` to ChromaDB so it can blend dense-vector
        similarity with BM25-style keyword matching.

        Falls back to pure dense ``similarity_search`` when *query_text*
        is empty or whitespace-only.
        """
        if not query_text or not query_text.strip():
            return await self.similarity_search(
                query_embedding, k, collection_name, metadata_filter
            )

        try:
            return await asyncio.to_thread(
                self._query_sync,
                query_embedding,
                k,
                collection_name,
                metadata_filter,
                query_text,
            )
        except Exception as exc:
            logger.error("ChromaDB hybrid search failed: %s", exc)
            raise RuntimeError(f"ChromaDB hybrid search failed: {exc}") from exc

    async def get_by_metadata(
        self,
        metadata_filter: dict[str, object],
        collection_name: str = "documents",
    ) -> list[Chunk]:
        """Retrieve chunks whose metadata matches all entries in *metadata_filter*.

        Used by incremental ingestion to find existing chunks with a
        given ``content_hash``. The filter is passed to ChromaDB as the
        ``where`` clause (server-side filtering).

        Args:
            metadata_filter: Metadata key-value pairs to match.
            collection_name: Name of the ChromaDB collection.

        Returns:
            A list of ``Chunk`` instances matching the filter.
            Empty list if the collection does not exist or has no matches.

        Raises:
            RuntimeError: If the ChromaDB get fails.
        """

        def _get() -> list[Chunk]:
            try:
                collection = self._client.get_collection(collection_name)
            except (ValueError, NotFoundError):
                return []

            if collection.count() == 0:
                return []

            results = collection.get(
                where=metadata_filter,
                include=["documents", "embeddings", "metadatas"],
            )

            chunks: list[Chunk] = []
            if not results or not results.get("ids"):
                return chunks

            chunk_ids = results["ids"]
            metadatas = results.get("metadatas") or []
            documents = results.get("documents") or []
            # NOTE: embeddings come back as a numpy array — never test it
            # for truthiness (ambiguous for multi-element arrays).
            embeddings = results.get("embeddings")

            for idx, chunk_id in enumerate(chunk_ids):
                metadata = dict(metadatas[idx]) if len(metadatas) > idx else {}
                document_id_str = metadata.pop("document_id", None)
                chunk_index = int(metadata.pop("chunk_index", 0))
                embedding_list = (
                    list(embeddings[idx])
                    if embeddings is not None and len(embeddings) > idx
                    else None
                )

                from uuid import UUID as _UUID

                chunks.append(
                    Chunk(
                        id=_UUID(chunk_id),
                        document_id=_UUID(document_id_str) if document_id_str else None,  # type: ignore[arg-type]
                        content=documents[idx] if len(documents) > idx else "",
                        embedding=embedding_list,
                        metadata=metadata,
                        chunk_index=chunk_index,
                    )
                )

            return chunks

        try:
            return await asyncio.to_thread(_get)
        except Exception as exc:
            logger.error("ChromaDB get_by_metadata failed: %s", exc)
            raise RuntimeError(f"ChromaDB get_by_metadata failed: {exc}") from exc

    async def list_documents(self, collection_name: str) -> list[dict]:
        """Return a summary per ingested document in the collection.

        Groups the stored chunks by their ``document_id`` metadata and
        returns one entry per document with its filename, size, chunk
        count, and creation timestamp.

        Args:
            collection_name: Name of the ChromaDB collection.

        Returns:
            A list of dicts with keys: ``document_id``, ``filename``,
            ``file_type``, ``file_size``, ``chunk_count``, ``created_at``.
            Empty list if the collection does not exist or is empty.

        Raises:
            RuntimeError: If listing the documents fails.
        """

        def _list() -> list[dict]:
            try:
                collection = self._client.get_collection(collection_name)
            except (ValueError, NotFoundError):
                return []

            if collection.count() == 0:
                return []

            data = collection.get(include=["metadatas"])
            documents: dict[str, dict[str, Any]] = {}
            for meta in data.get("metadatas") or []:
                if not meta:
                    continue
                document_id = meta.get("document_id")
                if not document_id:
                    continue
                entry = documents.setdefault(
                    str(document_id),
                    {
                        "document_id": str(document_id),
                        "filename": str(meta.get("filename", "unknown")),
                        "file_type": str(meta.get("file_type", "")),
                        "file_size": int(meta.get("file_size", 0) or 0),
                        "chunk_count": 0,
                        "created_at": str(meta.get("created_at", "")),
                    },
                )
                entry["chunk_count"] += 1

            return list(documents.values())

        try:
            return await asyncio.to_thread(_list)
        except Exception as exc:
            logger.error("ChromaDB list_documents failed: %s", exc)
            raise RuntimeError(f"ChromaDB list_documents failed: {exc}") from exc

    async def delete_by_metadata(self, filter_dict: dict, collection_name: str) -> None:
        """Delete chunks whose metadata matches all entries in *filter_dict*.

        Args:
            filter_dict: Metadata key-value pairs to match.  Values must
                be ``str``, ``int``, ``float``, or ``bool`` (ChromaDB
                metadata constraints).
            collection_name: Name of the ChromaDB collection.

        Raises:
            RuntimeError: If the deletion fails.
        """

        def _delete() -> None:
            try:
                collection = self._client.get_collection(collection_name)
            except (ValueError, NotFoundError):
                logger.debug(
                    "Collection '%s' does not exist — nothing to delete",
                    collection_name,
                )
                return

            if collection.count() == 0:
                return

            collection.delete(where=filter_dict)
            logger.info(
                "Deleted chunks matching %s from collection '%s'",
                filter_dict,
                collection_name,
            )

        try:
            await asyncio.to_thread(_delete)
        except Exception as exc:
            logger.error("ChromaDB delete_by_metadata failed: %s", exc)
            raise RuntimeError(f"ChromaDB delete failed: {exc}") from exc

    async def get_collection_count(self, collection_name: str) -> int:
        """Return the number of chunks in a collection.

        Args:
            collection_name: Name of the ChromaDB collection.

        Returns:
            The number of documents in the collection.  Returns ``0``
            if the collection does not exist.

        Raises:
            RuntimeError: If the count query fails.
        """

        def _count() -> int:
            try:
                collection = self._client.get_collection(collection_name)
                return collection.count()
            except (ValueError, NotFoundError):
                return 0

        try:
            return await asyncio.to_thread(_count)
        except Exception as exc:
            logger.error("ChromaDB get_collection_count failed: %s", exc)
            raise RuntimeError(f"ChromaDB count query failed: {exc}") from exc
