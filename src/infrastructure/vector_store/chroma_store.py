import asyncio
import logging
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.domain.interfaces.vector_store import VectorStore
from src.domain.value_objects.chunk import Chunk

logger = logging.getLogger(__name__)


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

        def _upsert() -> None:
            collection = self._get_or_create_collection(collection_name)

            ids: list[str] = []
            documents: list[str] = []
            embeddings: list[list[float]] = []
            metadatas: list[dict[str, Any]] = []

            for chunk in chunks:
                if chunk.embedding is None:
                    raise ValueError(
                        f"Chunk {chunk.id} has no embedding — "
                        "embeddings must be generated before storing."
                    )
                ids.append(str(chunk.id))
                documents.append(chunk.content)
                embeddings.append(chunk.embedding)
                metadatas.append(self._build_chroma_metadata(chunk))

            collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            logger.info(
                "Upserted %d chunks into collection '%s'",
                len(ids),
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
            raise RuntimeError(
                f"ChromaDB similarity search failed: {exc}"
            ) from exc

    def _query_sync(
        self,
        query_embedding: list[float],
        k: int,
        collection_name: str,
        metadata_filter: dict[str, object] | None = None,
    ) -> list[Chunk]:
        """Synchronous similarity search implementation.

        Args:
            query_embedding: The query vector.
            k: Number of results to return.
            collection_name: Name of the ChromaDB collection.
            metadata_filter: Optional metadata filter dict passed as
                ``where`` to ChromaDB.

        Returns:
            A list of ``Chunk`` instances ordered by relevance.
        """
        try:
            collection = self._client.get_collection(collection_name)
        except ValueError:
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
            metadata = (
                dict(metadatas[idx]) if len(metadatas) > idx else {}
            )
            document_id_str = metadata.pop("document_id", None)
            chunk_index = int(metadata.pop("chunk_index", 0))

            # Convert cosine distance to similarity score
            if len(distances) > idx:
                metadata["score"] = round(
                    1.0 - float(distances[idx]), 4
                )

            from uuid import UUID

            embedding_list = (
                list(embeddings[idx])
                if len(embeddings) > idx
                else None
            )

            chunk = Chunk(
                id=UUID(ids[idx]),
                document_id=UUID(document_id_str)  # type: ignore[arg-type]
                if document_id_str
                else None,
                content=documents[idx]
                if len(documents) > idx
                else "",
                embedding=embedding_list,
                metadata=metadata,
                chunk_index=chunk_index,
            )
            chunks.append(chunk)

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
                self._hybrid_search_sync,
                query_embedding,
                query_text,
                k,
                collection_name,
                metadata_filter,
            )
        except Exception as exc:
            logger.error("ChromaDB hybrid search failed: %s", exc)
            raise RuntimeError(
                f"ChromaDB hybrid search failed: {exc}"
            ) from exc

    def _hybrid_search_sync(
        self,
        query_embedding: list[float],
        query_text: str,
        k: int,
        collection_name: str,
        metadata_filter: dict[str, object] | None = None,
    ) -> list[Chunk]:
        """Synchronous hybrid search implementation.

        Passes both ``query_embeddings`` and ``query_texts`` to
        ChromaDB's ``query()`` so it blends dense-vector similarity
        with BM25-style keyword matching.

        Args:
            query_embedding: The dense query vector.
            query_text:      The text query for keyword matching.
            k:               Number of results to return.
            collection_name: ChromaDB collection to search.
            metadata_filter: Optional metadata filter dict passed as
                ``where`` to ChromaDB.

        Returns:
            A list of ``Chunk`` instances ordered by relevance.
            Empty list if the collection is missing or empty.
        """
        try:
            collection = self._client.get_collection(collection_name)
        except ValueError:
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
        embeddings_list = results.get("embeddings", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for idx in range(len(ids)):
            metadata = (
                dict(metadatas[idx]) if len(metadatas) > idx else {}
            )
            document_id_str = metadata.pop("document_id", None)
            chunk_index = int(metadata.pop("chunk_index", 0))

            if len(distances) > idx:
                metadata["score"] = round(
                    1.0 - float(distances[idx]), 4
                )

            from uuid import UUID

            embedding_list = (
                list(embeddings_list[idx])
                if len(embeddings_list) > idx
                else None
            )

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
            "hybrid_search returned %d chunks from '%s'",
            len(chunks),
            collection_name,
        )
        return chunks

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
            except ValueError:
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
            except ValueError:
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
            except ValueError:
                return 0

        try:
            return await asyncio.to_thread(_count)
        except Exception as exc:
            logger.error("ChromaDB get_collection_count failed: %s", exc)
            raise RuntimeError(f"ChromaDB count query failed: {exc}") from exc
