"""Tests for the document management API routes."""

import io
import re
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile

from src.presentation.api.routes import documents as documents_router


async def _run_background(tasks: BackgroundTasks) -> None:
    """Execute everything the route queued on this BackgroundTasks.

    Ingestion now happens after the response is sent, so a direct handler call
    only *schedules* it. Anything asserting on the use case has to run this
    first, or it is asserting on a task that never fired.
    """
    for task in list(tasks.tasks):
        result = task.func(*task.args, **task.kwargs)
        if hasattr(result, "__await__"):
            await result


def _background() -> BackgroundTasks:
    """A real BackgroundTasks for direct handler calls.

    The route queues ingestion on this rather than awaiting it, so the tests get
    the 202 the client would see and can inspect `tasks.tasks` for the work that
    was scheduled. It is never executed here — running it would require the
    background machinery the app lifespan sets up.
    """
    return BackgroundTasks()


class TestUploadDocumentSizeLimit:
    """Uploads must be rejected *before* the whole body is buffered in memory.

    Starlette spools the request body to a temp file with no upper bound and
    ``file.read()`` would pull all of it into RAM, so an uncapped read is a
    trivial way to exhaust memory (and DOCX/PDF parsing then expands it again).
    """

    def _settings(self, max_mb: int = 50) -> MagicMock:
        settings = MagicMock()
        settings.MAX_FILE_SIZE_MB = max_mb
        return settings

    @pytest.mark.asyncio
    @patch("src.presentation.api.routes.documents.get_settings")
    async def test_rejects_upload_larger_than_limit_via_declared_size(
        self, mock_get_settings
    ):
        mock_get_settings.return_value = self._settings(max_mb=1)
        # Content-Length says 5 MB, which is over the 1 MB cap.
        oversized = UploadFile(filename="big.pdf", file=io.BytesIO(b"x" * 1024))
        oversized.size = 5 * 1024 * 1024

        with pytest.raises(HTTPException) as exc_info:
            await documents_router.upload_document(_background(), oversized)

        assert exc_info.value.status_code == 413
        assert "too large" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("src.presentation.api.routes.documents.get_settings")
    async def test_rejects_upload_that_exceeds_limit_while_streaming(
        self, mock_get_settings
    ):
        """A chunked request can omit Content-Length, so count bytes too."""
        mock_get_settings.return_value = self._settings(max_mb=1)
        undeclared = UploadFile(
            filename="big.pdf", file=io.BytesIO(b"x" * (2 * 1024 * 1024))
        )
        undeclared.size = None  # client did not declare a length

        with pytest.raises(HTTPException) as exc_info:
            await documents_router.upload_document(_background(), undeclared)

        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    @patch("src.application.use_cases.ingest_document.IngestDocumentUseCase")
    @patch("src.presentation.api.routes.documents._get_dependencies")
    @patch("src.presentation.api.routes.documents.get_settings")
    async def test_accepts_upload_under_the_limit(
        self, mock_get_settings, mock_get_deps, mock_use_case_cls
    ):
        mock_get_settings.return_value = self._settings(max_mb=1)
        mock_get_deps.return_value = (AsyncMock(), AsyncMock())

        settings = mock_get_settings.return_value
        settings.ENABLE_PARENT_CHILD = False
        settings.ENABLE_SEMANTIC_CHUNKING = False

        mock_uc = mock_use_case_cls.return_value
        mock_uc.execute = AsyncMock(
            return_value={
                "document_id": "abc",
                "filename": "test.pdf",
                "chunk_count": 1,
                "message": "ok",
            }
        )

        small = UploadFile(filename="test.pdf", file=io.BytesIO(b"%PDF-1.4 small"))

        response = await documents_router.upload_document(_background(), small)

        # The route now mints the id itself, so the client can poll
        # /documents/status/{id} immediately; the use case's own id is internal.
        assert response.document_id != "abc"
        UUID(response.document_id)  # raises if it is not a valid uuid
        assert response.status == "pending"
        assert response.chunk_count == 0


class TestUploadDocumentSplitterSelection:
    """The upload route must select the splitter per feature flags."""

    def _make_file(self) -> UploadFile:
        return UploadFile(filename="test.pdf", file=io.BytesIO(b"%PDF-1.4 fake"))

    @pytest.mark.asyncio
    @patch("src.application.use_cases.ingest_document.IngestDocumentUseCase")
    @patch("src.presentation.api.routes.documents._get_dependencies")
    @patch("src.presentation.api.routes.documents.get_settings")
    async def test_upload_uses_text_splitter_when_parent_child_disabled(
        self, mock_get_settings, mock_get_deps, mock_use_case_cls
    ):
        """With all features off, the plain TextSplitter is used."""
        from src.infrastructure.document_processing.text_splitter import TextSplitter

        settings = MagicMock()
        settings.MAX_FILE_SIZE_MB = 50
        settings.ENABLE_PARENT_CHILD = False
        settings.ENABLE_SEMANTIC_CHUNKING = False
        mock_get_settings.return_value = settings
        mock_get_deps.return_value = (AsyncMock(), AsyncMock())

        mock_uc = mock_use_case_cls.return_value
        mock_uc.execute = AsyncMock(
            return_value={
                "document_id": "abc",
                "filename": "test.pdf",
                "chunk_count": 1,
                "message": "ok",
            }
        )

        background = _background()
        await documents_router.upload_document(background, self._make_file())
        await _run_background(background)

        _, kwargs = mock_use_case_cls.call_args
        assert isinstance(kwargs["text_splitter"], TextSplitter)


class TestDeleteDocument:
    """Deleting a document removes its chunks from the active collection."""

    @pytest.mark.asyncio
    @patch("src.presentation.api.routes.documents._get_dependencies")
    @patch("src.presentation.api.routes.documents.get_settings")
    async def test_delete_removes_chunks_from_active_collection(
        self, mock_get_settings, mock_get_deps
    ):
        """Delete targets the single configured collection and reports success."""
        settings = MagicMock()
        settings.MAX_FILE_SIZE_MB = 50
        settings.CHROMA_COLLECTION_NAME = "documents"
        mock_get_settings.return_value = settings

        vector_store = AsyncMock()
        vector_store.delete_by_metadata = AsyncMock()
        mock_get_deps.return_value = (vector_store, AsyncMock())

        result = await documents_router.delete_document("doc-123")

        assert "deleted" in result["message"]
        collections = [
            call.args[1] for call in vector_store.delete_by_metadata.call_args_list
        ]
        assert collections == ["documents"]

    @pytest.mark.asyncio
    @patch("src.presentation.api.routes.documents._get_dependencies")
    @patch("src.presentation.api.routes.documents.get_settings")
    async def test_delete_propagates_store_failure_as_http_error(
        self, mock_get_settings, mock_get_deps
    ):
        """A store failure must surface as a 500, not a silent success."""
        settings = MagicMock()
        settings.MAX_FILE_SIZE_MB = 50
        settings.CHROMA_COLLECTION_NAME = "documents"
        mock_get_settings.return_value = settings

        vector_store = AsyncMock()
        vector_store.delete_by_metadata = AsyncMock(side_effect=RuntimeError("boom"))
        mock_get_deps.return_value = (vector_store, AsyncMock())

        with pytest.raises(HTTPException) as exc:
            await documents_router.delete_document("doc-123")
        assert exc.value.status_code == 500


class TestUploadWiring:
    """Guard the upload route's wiring itself.

    ponytail: this exists because every other test here patches
    IngestDocumentUseCase wholesale, so nothing ever constructed the real one —
    a stale keyword argument in the route survived a green suite and only
    surfaced on a real upload. Now the route's actual call is inspected against
    the constructor's real signature, which is where an arity mismatch shows.
    """

    def test_route_passes_only_kwargs_the_use_case_accepts(self):
        import inspect

        from src.application.use_cases.ingest_document import IngestDocumentUseCase

        # The construction moved into _run_ingestion when uploads became
        # asynchronous; inspecting upload_document would now find no call at all
        # and pass for the wrong reason.
        route_src = inspect.getsource(documents_router._run_ingestion)
        accepted = set(inspect.signature(IngestDocumentUseCase.__init__).parameters) - {
            "self"
        }

        # Keywords inside the IngestDocumentUseCase(...) call specifically.
        call = re.search(r"IngestDocumentUseCase\((.*?)\n        \)", route_src, re.S)
        assert call, "could not find the IngestDocumentUseCase(...) call"

        supplied = set(re.findall(r"(\w+)=", call.group(1)))
        assert supplied, "expected the route to pass constructor kwargs"
        assert supplied <= accepted, (
            "upload_document passes kwargs the use case does not accept: "
            f"{sorted(supplied - accepted)}"
        )


class TestDeleteAllDocuments:
    """The Danger Zone's bulk delete, which must not half-claim success."""

    def _doc(self, doc_id: str) -> dict:
        return {
            "document_id": doc_id,
            "filename": f"{doc_id}.pdf",
            "file_type": ".pdf",
            "file_size": 10,
            "chunk_count": 1,
            "created_at": "2026-01-01T00:00:00",
        }

    @pytest.mark.asyncio
    @patch("src.presentation.api.routes.documents.get_settings")
    async def test_deletes_every_listed_document(self, mock_get_settings):
        settings = MagicMock()
        settings.CHROMA_COLLECTION_NAME = "documents"
        mock_get_settings.return_value = settings

        store = MagicMock()
        store.list_documents = AsyncMock(return_value=[self._doc("a"), self._doc("b")])
        store.delete_by_metadata = AsyncMock()
        documents_router._vector_store.set(store)
        documents_router._embedding_provider.set(MagicMock())

        result = await documents_router.delete_all_documents()

        assert result["deleted"] == 2
        assert result["failed"] == 0
        assert store.delete_by_metadata.await_count == 2

    @pytest.mark.asyncio
    @patch("src.presentation.api.routes.documents.get_settings")
    async def test_continues_past_a_failing_document(self, mock_get_settings):
        settings = MagicMock()
        settings.CHROMA_COLLECTION_NAME = "documents"
        mock_get_settings.return_value = settings

        store = MagicMock()
        store.list_documents = AsyncMock(
            return_value=[self._doc("a"), self._doc("bad")]
        )
        store.delete_by_metadata = AsyncMock(side_effect=[None, RuntimeError("boom")])
        documents_router._vector_store.set(store)
        documents_router._embedding_provider.set(MagicMock())

        result = await documents_router.delete_all_documents()

        # The good document still went; the failure is reported, not hidden.
        assert result["deleted"] == 1
        assert result["failed"] == 1

    @pytest.mark.asyncio
    @patch("src.presentation.api.routes.documents.get_settings")
    async def test_500_when_every_delete_fails(self, mock_get_settings):
        settings = MagicMock()
        settings.CHROMA_COLLECTION_NAME = "documents"
        mock_get_settings.return_value = settings

        store = MagicMock()
        store.list_documents = AsyncMock(return_value=[self._doc("a")])
        store.delete_by_metadata = AsyncMock(side_effect=RuntimeError("boom"))
        documents_router._vector_store.set(store)
        documents_router._embedding_provider.set(MagicMock())

        with pytest.raises(HTTPException) as exc_info:
            await documents_router.delete_all_documents()
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    @patch("src.presentation.api.routes.documents.get_settings")
    async def test_empty_library_is_a_clean_no_op(self, mock_get_settings):
        settings = MagicMock()
        settings.CHROMA_COLLECTION_NAME = "documents"
        mock_get_settings.return_value = settings

        store = MagicMock()
        store.list_documents = AsyncMock(return_value=[])
        documents_router._vector_store.set(store)
        documents_router._embedding_provider.set(MagicMock())

        result = await documents_router.delete_all_documents()

        assert result["deleted"] == 0
        store.delete_by_metadata.assert_not_called()
