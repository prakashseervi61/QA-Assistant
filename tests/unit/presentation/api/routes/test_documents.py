"""Tests for the document management API routes."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from src.presentation.api.routes import documents as documents_router


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
            await documents_router.upload_document(oversized)

        assert exc_info.value.status_code == 413
        assert "too large" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("src.presentation.api.routes.documents.get_settings")
    async def test_rejects_upload_that_exceeds_limit_while_streaming(
        self, mock_get_settings
    ):
        """A chunked request can omit Content-Length, so count bytes too."""
        mock_get_settings.return_value = self._settings(max_mb=1)
        undeclared = UploadFile(filename="big.pdf", file=io.BytesIO(b"x" * (2 * 1024 * 1024)))
        undeclared.size = None  # client did not declare a length

        with pytest.raises(HTTPException) as exc_info:
            await documents_router.upload_document(undeclared)

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
        settings.ENABLE_CHUNK_ENRICHMENT = False

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

        response = await documents_router.upload_document(small)

        assert response.document_id == "abc"


class TestUploadDocumentSplitterSelection:
    """The upload route must select the splitter per feature flags."""

    def _make_file(self) -> UploadFile:
        return UploadFile(filename="test.pdf", file=io.BytesIO(b"%PDF-1.4 fake"))

    @pytest.mark.asyncio
    @patch("src.application.use_cases.ingest_document.IngestDocumentUseCase")
    @patch("src.presentation.api.routes.documents._get_dependencies")
    @patch("src.presentation.api.routes.documents.get_settings")
    async def test_upload_constructs_parent_child_splitter_when_enabled(
        self, mock_get_settings, mock_get_deps, mock_use_case_cls
    ):
        """C2: documents.py builds a ParentChildSplitter when the flag is on."""
        from src.infrastructure.document_processing.parent_child_splitter import (
            ParentChildSplitter,
        )

        settings = MagicMock()
        settings.MAX_FILE_SIZE_MB = 50
        settings.ENABLE_PARENT_CHILD = True
        settings.PARENT_CHUNK_SIZE = 1500
        settings.CHILD_CHUNK_SIZE = 300
        settings.CHILD_CHUNK_OVERLAP = 75
        settings.ENABLE_SEMANTIC_CHUNKING = False
        settings.ENABLE_CHUNK_ENRICHMENT = False
        mock_get_settings.return_value = settings
        mock_get_deps.return_value = (AsyncMock(), AsyncMock())

        mock_uc = mock_use_case_cls.return_value
        mock_uc.execute = AsyncMock(
            return_value={
                "document_id": "abc",
                "filename": "test.pdf",
                "chunk_count": 3,
                "message": "ok",
            }
        )

        response = await documents_router.upload_document(self._make_file())

        _, kwargs = mock_use_case_cls.call_args
        splitter = kwargs["text_splitter"]
        assert isinstance(splitter, ParentChildSplitter)
        assert splitter.parent_chunk_size == 1500
        assert splitter.child_chunk_size == 300
        assert splitter.child_overlap == 75
        assert response.document_id == "abc"

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
        settings.ENABLE_CHUNK_ENRICHMENT = False
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

        await documents_router.upload_document(self._make_file())

        _, kwargs = mock_use_case_cls.call_args
        assert isinstance(kwargs["text_splitter"], TextSplitter)


class TestDeleteDocument:
    @pytest.mark.asyncio
    @patch("src.presentation.api.routes.documents._get_dependencies")
    @patch("src.presentation.api.routes.documents.get_settings")
    async def test_delete_cleans_parent_and_child_collections(
        self, mock_get_settings, mock_get_deps
    ):
        """M3: delete removes chunks from main, parent, and child collections."""
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
        assert collections == ["documents", "documents_parent", "documents_child"]

    @pytest.mark.asyncio
    @patch("src.presentation.api.routes.documents._get_dependencies")
    @patch("src.presentation.api.routes.documents.get_settings")
    async def test_delete_ignores_parent_child_cleanup_failures(
        self, mock_get_settings, mock_get_deps
    ):
        """M3: a failure cleaning an optional parent/child collection does
        not fail the request; the main-collection delete must succeed."""
        settings = MagicMock()
        settings.MAX_FILE_SIZE_MB = 50
        settings.CHROMA_COLLECTION_NAME = "documents"
        mock_get_settings.return_value = settings

        vector_store = AsyncMock()
        vector_store.delete_by_metadata = AsyncMock(
            side_effect=[None, RuntimeError("collection missing"), None]
        )
        mock_get_deps.return_value = (vector_store, AsyncMock())

        result = await documents_router.delete_document("doc-123")

        assert "deleted" in result["message"]
        assert vector_store.delete_by_metadata.call_count == 3
