"""Tests for the settings routes — API key handling, config, and export."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.infrastructure.llm.api_key_resolver import (
    SOURCE_ENV,
    SOURCE_NONE,
    SOURCE_USER,
)
from src.presentation.api.routes import settings as settings_router


@pytest.fixture(autouse=True)
def _restore_registries():
    """Snapshot and restore the router registries around every test.

    These are module-level singletons, so without this a test that unwires one
    would silently change the behaviour of whichever test runs next.
    """
    registries = (
        settings_router._store,
        settings_router._resolver,
        settings_router._vector_store,
        settings_router._conversations,
    )
    saved = [r._instance for r in registries]
    try:
        yield
    finally:
        for registry, instance in zip(registries, saved, strict=True):
            registry._instance = instance


class _FakeStore:
    """Stateful store double.

    A ``MagicMock`` would keep returning the old key after ``clear_api_key()``,
    which would make the precedence tests pass for the wrong reason. This one
    actually mutates, so "clearing falls back to env" is genuinely exercised.
    """

    def __init__(self, key: str | None = None) -> None:
        self.key = key
        self.set_calls: list[str] = []
        self.clear_calls = 0

    def get_api_key(self) -> str | None:
        return self.key

    def set_api_key(self, api_key: str) -> None:
        self.key = api_key
        self.set_calls.append(api_key)

    def clear_api_key(self) -> None:
        self.key = None
        self.clear_calls += 1


def _wire(store=None, resolver=None, vector_store=None, repo=None):
    """Register test doubles with the router's startup registries."""
    settings_router._store.set(store or _FakeStore())
    settings_router._resolver.set(resolver or MagicMock())
    settings_router._vector_store.set(vector_store or MagicMock())
    settings_router._conversations.set(repo or MagicMock())


def _resolver(*, user_key=None, env_key=""):
    """Build a real resolver over a stateful store, so precedence is genuine."""
    from src.infrastructure.llm.api_key_resolver import ApiKeyResolver

    store = _FakeStore(user_key)
    settings = MagicMock()
    settings.GEMINI_API_KEY = env_key
    return store, ApiKeyResolver(store, settings)


class TestApiKeyStatus:
    @pytest.mark.asyncio
    async def test_reports_a_configured_user_key_without_leaking_it(self):
        secret = "fake-key-DO-NOT-USE-0123456789abcdefghij"
        store, resolver = _resolver(user_key=secret)
        _wire(store=store, resolver=resolver)

        status = await settings_router.get_api_key_status()

        assert status.configured is True
        assert status.source == SOURCE_USER
        assert "DO-NOT-USE" not in status.masked
        assert status.masked.endswith("ghij")

    @pytest.mark.asyncio
    async def test_reports_the_env_source(self):
        store, resolver = _resolver(user_key=None, env_key="env-key-value")
        _wire(store=store, resolver=resolver)

        status = await settings_router.get_api_key_status()

        assert status.source == SOURCE_ENV
        assert status.configured is True

    @pytest.mark.asyncio
    async def test_reports_none_when_unconfigured(self):
        store, resolver = _resolver(user_key=None, env_key="")
        _wire(store=store, resolver=resolver)

        status = await settings_router.get_api_key_status()

        assert status.configured is False
        assert status.source == SOURCE_NONE
        assert status.masked is None

    @pytest.mark.asyncio
    async def test_raises_503_when_startup_never_wired_the_resolver(self):
        # This is the guard that turns a missing startup wiring into a clear
        # 503 instead of an AttributeError deep inside the handler.
        settings_router._resolver.set(None)
        with pytest.raises(HTTPException) as exc_info:
            await settings_router.get_api_key_status()
        assert exc_info.value.status_code == 503


class TestPutApiKey:
    @pytest.mark.asyncio
    async def test_stores_the_key_and_returns_only_a_mask(self):
        store, resolver = _resolver(user_key=None)
        _wire(store=store, resolver=resolver)
        secret = "fake-key-DO-NOT-USE-0123456789abcdefghij"

        status = await settings_router.put_api_key(
            settings_router.ApiKeyUpdate(api_key=secret)
        )

        assert store.set_calls == [secret]
        assert status.source == SOURCE_USER
        assert "DO-NOT-USE" not in status.masked

    @pytest.mark.asyncio
    async def test_trims_surrounding_whitespace(self):
        store, resolver = _resolver(user_key=None)
        _wire(store=store, resolver=resolver)

        await settings_router.put_api_key(
            settings_router.ApiKeyUpdate(api_key="  padded-key-value  ")
        )

        assert store.set_calls == ["padded-key-value"]

    @pytest.mark.parametrize("bad_key", ["short", "has space inside", "tab\there"])
    def test_rejects_malformed_keys_before_they_are_stored(self, bad_key):
        # Whitespace and over-short values are paste accidents; rejecting them
        # here gives an actionable message instead of an opaque Google 401.
        with pytest.raises(ValidationError):
            settings_router.ApiKeyUpdate(api_key=bad_key)

    @pytest.mark.asyncio
    async def test_rejected_key_is_never_written(self):
        store, resolver = _resolver(user_key=None)
        _wire(store=store, resolver=resolver)

        with pytest.raises(ValidationError):
            await settings_router.put_api_key(
                settings_router.ApiKeyUpdate(api_key="a key with spaces")
            )

        assert store.set_calls == []


class TestDeleteApiKey:
    @pytest.mark.asyncio
    async def test_clearing_falls_back_to_the_env_key(self):
        store, resolver = _resolver(user_key="user-key-value", env_key="env-key-value")
        _wire(store=store, resolver=resolver)

        status = await settings_router.delete_api_key()

        assert store.clear_calls == 1
        assert status.source == SOURCE_ENV

    @pytest.mark.asyncio
    async def test_clearing_with_no_env_key_reports_none(self):
        store, resolver = _resolver(user_key="user-key-value", env_key="")
        _wire(store=store, resolver=resolver)

        status = await settings_router.delete_api_key()

        assert status.configured is False
        assert status.source == SOURCE_NONE
        assert status.masked is None


class TestGetAppConfig:
    @pytest.mark.asyncio
    async def test_returns_storage_stats_and_never_the_api_key(self):
        store, resolver = _resolver(user_key="fake-key-DO-NOT-USE", env_key="")
        vector_store = MagicMock()
        vector_store.list_documents = AsyncMock(
            return_value=[
                {
                    "document_id": "d1",
                    "filename": "a.pdf",
                    "file_type": ".pdf",
                    "file_size": 100,
                    "chunk_count": 4,
                    "created_at": "2026-01-01T00:00:00",
                }
            ]
        )
        vector_store.get_collection_count = AsyncMock(return_value=4)
        _wire(store=store, resolver=resolver, vector_store=vector_store)

        from src.infrastructure.config.settings import get_settings

        payload = await settings_router.get_app_config(settings=get_settings())
        serialised = payload.model_dump_json()

        assert payload.document_count == 1
        assert payload.chunk_count == 4
        # The config endpoint is an allow-list, so no credential can appear.
        assert "fake-key-DO-NOT-USE" not in serialised
        assert "api_key" not in serialised

    @pytest.mark.asyncio
    async def test_surfaces_a_read_failure_as_500(self):
        store, resolver = _resolver()
        vector_store = MagicMock()
        vector_store.list_documents = AsyncMock(side_effect=RuntimeError("boom"))
        _wire(store=store, resolver=resolver, vector_store=vector_store)

        from src.infrastructure.config.settings import get_settings

        with pytest.raises(HTTPException) as exc_info:
            await settings_router.get_app_config(settings=get_settings())
        assert exc_info.value.status_code == 500


class TestDirectorySize:
    def test_missing_path_is_zero(self, tmp_path):
        assert settings_router._directory_size(tmp_path / "nope") == 0

    def test_file_size(self, tmp_path):
        target = tmp_path / "history.db"
        target.write_bytes(b"x" * 123)
        assert settings_router._directory_size(target) == 123

    def test_directory_size_sums_the_tree(self, tmp_path):
        (tmp_path / "chroma").mkdir()
        (tmp_path / "chroma" / "a.bin").write_bytes(b"x" * 10)
        (tmp_path / "chroma" / "b.bin").write_bytes(b"x" * 5)
        assert settings_router._directory_size(tmp_path / "chroma") == 15


class TestExportFormats:
    """The endpoint kept its JSON default; the rest are new downloads."""

    def _vector_store(self):
        vector_store = MagicMock()
        vector_store.list_documents = AsyncMock(
            return_value=[
                {
                    "document_id": "d1",
                    "filename": "notes.pdf",
                    "file_type": ".pdf",
                    "file_size": 2048,
                    "chunk_count": 12,
                    "created_at": "2026-10-01",
                }
            ]
        )
        return vector_store

    def _repo(self):
        conversation = MagicMock()
        conversation.id = "c1"
        conversation.title = "What is RSA?"
        conversation.created_at = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
        conversation.updated_at = None
        message = MagicMock()
        message.id = "m1"
        message.role = "assistant"
        message.content = "RSA is an asymmetric cipher."
        message.created_at = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
        message.sources = [{"metadata": {"filename": "notes.pdf"}}]
        repo = MagicMock()
        repo.list_conversations = AsyncMock(return_value=[conversation])
        repo.get_messages = AsyncMock(return_value=[message])
        return repo

    async def _export(self, fmt=None):
        _wire(
            store=MagicMock(),
            resolver=MagicMock(),
            vector_store=self._vector_store(),
            repo=self._repo(),
        )
        from src.infrastructure.config.settings import get_settings

        kwargs = {"settings": get_settings()}
        if fmt is not None:
            kwargs["format"] = fmt
        return await settings_router.export_data(**kwargs)

    @pytest.mark.asyncio
    async def test_defaults_to_json_with_no_attachment_header(self):
        """Backwards compatibility: an existing caller passing no format must
        still get the same body and the same headers."""
        response = await self._export()
        assert response.media_type == "application/json"
        assert "content-disposition" not in response.headers
        body = json.loads(response.body)
        assert body["app_version"] == "0.1.0"
        assert body["documents"][0]["filename"] == "notes.pdf"

    @pytest.mark.asyncio
    async def test_explicit_json_matches_the_default(self):
        response = await self._export("json")
        assert response.media_type == "application/json"
        assert json.loads(response.body)["conversations"][0]["title"] == "What is RSA?"

    @pytest.mark.asyncio
    async def test_markdown_download(self):
        response = await self._export("markdown")
        assert response.media_type.startswith("text/markdown")
        assert "attachment" in response.headers["content-disposition"]
        assert '.md"' in response.headers["content-disposition"]
        text = response.body.decode()
        assert "RSA is an asymmetric cipher." in text
        assert "notes.pdf" in text

    @pytest.mark.asyncio
    async def test_text_download(self):
        response = await self._export("text")
        assert response.media_type.startswith("text/plain")
        assert '.txt"' in response.headers["content-disposition"]
        assert "[ASSISTANT]" in response.body.decode()

    @pytest.mark.asyncio
    async def test_pdf_download_starts_with_the_pdf_header(self):
        response = await self._export("pdf")
        assert response.media_type == "application/pdf"
        assert '.pdf"' in response.headers["content-disposition"]
        assert response.body.startswith(b"%PDF-1.4")

    @pytest.mark.asyncio
    async def test_rejects_an_unknown_format_with_400(self):
        with pytest.raises(HTTPException) as exc_info:
            await self._export("docx")
        assert exc_info.value.status_code == 400
        assert "docx" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_all_formats_share_one_payload(self):
        """The bundle is built once; only the rendering differs. If one format
        ever dropped a conversation, this is what would notice.

        Case-insensitive because the plain-text and PDF renderers set the
        conversation title as an upper-case section header, which is deliberate
        styling rather than a different payload.
        """
        found = []
        for fmt in ("json", "markdown", "text", "pdf"):
            response = await self._export(fmt)
            found.append(b"what is rsa?" in response.body.lower())
        assert found == [True, True, True, True]
