"""Tests for the observability tracer wrapper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _fake_otel_modules(exporter_cls: MagicMock) -> dict[str, object]:
    """Build a fake opentelemetry package tree for sys.modules patching.

    OpenTelemetry is an optional dependency (see the ``tracing`` extra in
    pyproject.toml), so the real package may not be installed. Every module
    the tracer imports is faked; the OTLP exporter class is the object
    under test.
    """
    return {
        "opentelemetry": MagicMock(),
        "opentelemetry.exporter": MagicMock(),
        "opentelemetry.exporter.otlp": MagicMock(),
        "opentelemetry.exporter.otlp.proto": MagicMock(),
        "opentelemetry.exporter.otlp.proto.http": MagicMock(),
        "opentelemetry.exporter.otlp.proto.http.trace_exporter": MagicMock(
            OTLPSpanExporter=exporter_cls
        ),
        "opentelemetry.sdk": MagicMock(),
        "opentelemetry.sdk.resources": MagicMock(),
        "opentelemetry.sdk.trace": MagicMock(),
        "opentelemetry.sdk.trace.export": MagicMock(),
    }


class TestTracerFactory:
    """Tests for create_tracer()."""

    def test_create_tracer_returns_none_when_disabled(self):
        """Tracing disabled -> no tracer."""
        from src.infrastructure.observability.tracer import create_tracer

        with patch(
            "src.infrastructure.observability.tracer.get_settings"
        ) as mock_settings:
            settings = MagicMock()
            settings.ENABLE_TRACING = False
            mock_settings.return_value = settings

            tracer = create_tracer()
            assert tracer is None

    def test_create_tracer_returns_noop_when_deps_missing(self):
        """Tracing enabled but opentelemetry missing -> no-op tracer (never crash)."""
        from src.infrastructure.observability.tracer import create_tracer

        with (
            patch(
                "src.infrastructure.observability.tracer.get_settings"
            ) as mock_settings,
            patch.dict(
                "sys.modules",
                {"opentelemetry": None, "opentelemetry.sdk": None},
            ),
        ):
            settings = MagicMock()
            settings.ENABLE_TRACING = True
            mock_settings.return_value = settings

            tracer = create_tracer()
            # Should not crash; returns a no-op tracer object or None
            assert tracer is not None

    def test_enabled_tracer_is_used(self):
        """When enabled with deps available, a real tracer object is returned."""
        from src.infrastructure.observability.tracer import create_tracer

        mock_tracer = MagicMock()
        with (
            patch(
                "src.infrastructure.observability.tracer.get_settings"
            ) as mock_settings,
            patch(
                "src.infrastructure.observability.tracer._create_opentelemetry_tracer",
                return_value=mock_tracer,
            ),
        ):
            settings = MagicMock()
            settings.ENABLE_TRACING = True
            mock_settings.return_value = settings

            tracer = create_tracer()
            assert tracer is mock_tracer


class TestCreateOpenTelemetryTracer:
    """Tests exercising the real _create_opentelemetry_tracer() path.

    The OpenTelemetry packages are faked via sys.modules so the tests run
    without the optional ``tracing`` extra installed; the OTLP exporter
    class is the real object under test.
    """

    def test_exporter_constructed_without_insecure_kwarg(self):
        """HTTP OTLP exporter is called with endpoint and no insecure kwarg.

        Regression test: ``insecure=True`` is gRPC-exporter-only. Passing it
        to the HTTP exporter raised TypeError inside the broad except, which
        silently downgraded tracing to the no-op tracer.
        """
        from src.infrastructure.observability import tracer

        exporter_cls = MagicMock()
        settings = MagicMock()
        settings.TRACING_ENDPOINT = "http://phoenix:6006/v1/traces"
        settings.TRACING_SERVICE_NAME = "qa-assistant"

        with (
            patch(
                "src.infrastructure.observability.tracer.get_settings",
                return_value=settings,
            ),
            patch.dict("sys.modules", _fake_otel_modules(exporter_cls)),
        ):
            result = tracer._create_opentelemetry_tracer()

        assert result is not None
        exporter_cls.assert_called_once()
        call_kwargs = exporter_cls.call_args.kwargs
        assert call_kwargs.get("endpoint") == "http://phoenix:6006/v1/traces"
        assert "insecure" not in call_kwargs

    def test_exporter_construction_failure_returns_none(self):
        """Exporter failures are contained — never raise out of the tracer."""
        from src.infrastructure.observability import tracer

        settings = MagicMock()
        settings.TRACING_ENDPOINT = "http://phoenix:6006/v1/traces"
        settings.TRACING_SERVICE_NAME = "qa-assistant"

        def _explode(*args, **kwargs):
            raise TypeError("boom")

        with (
            patch(
                "src.infrastructure.observability.tracer.get_settings",
                return_value=settings,
            ),
            patch.dict(
                "sys.modules",
                _fake_otel_modules(MagicMock(side_effect=_explode)),
            ),
        ):
            result = tracer._create_opentelemetry_tracer()

        assert result is None


class TestNoopTracer:
    """The no-op tracer must be a safe drop-in."""

    def test_noop_tracer_span_context_manager(self):
        """start_as_current_span works as a context manager."""
        from src.infrastructure.observability.tracer import NoopTracer

        tracer = NoopTracer()
        with tracer.start_as_current_span("test") as span:
            span.set_attribute("key", "value")
        # No exceptions raised

    def test_noop_tracer_methods_exist(self):
        """NoopTracer exposes the same surface as the real one."""
        from src.infrastructure.observability.tracer import NoopTracer

        tracer = NoopTracer()
        assert callable(getattr(tracer, "start_as_current_span"))
        assert callable(getattr(tracer, "start_span"))


class TestRAGEngineTracing:
    """RAGEngine spans are created when a tracer is injected."""

    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        llm.generate = AsyncMock(return_value="This is the answer.")
        llm.get_usage = AsyncMock(return_value={})
        return llm

    @pytest.fixture
    def mock_embedding(self):
        emb = AsyncMock()
        emb.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
        emb.embed_batch = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        emb.get_embedding_dimension = MagicMock(return_value=3)
        return emb

    @pytest.fixture
    def mock_vector_store(self):
        store = AsyncMock()
        store.similarity_search = AsyncMock(return_value=[])
        store.hybrid_search = AsyncMock(return_value=[])
        store.add_documents = AsyncMock()
        store.get_collection_count = AsyncMock(return_value=0)
        return store

    @pytest.mark.asyncio
    async def test_query_uses_tracer_when_injected(
        self, mock_llm, mock_embedding, mock_vector_store
    ):
        """RAGEngine calls tracer.start_as_current_span when tracer provided."""
        from src.application.services.rag_engine import RAGEngine

        mock_tracer = MagicMock()
        span_cm = MagicMock()
        span = MagicMock()
        span_cm.__enter__ = MagicMock(return_value=span)
        span_cm.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = span_cm

        engine = RAGEngine(
            llm_provider=mock_llm,
            embedding_provider=mock_embedding,
            vector_store=mock_vector_store,
            tracer=mock_tracer,
        )
        result = await engine.query("What is RAG?")
        assert result is not None
        assert mock_tracer.start_as_current_span.call_count >= 1

    @pytest.mark.asyncio
    async def test_query_without_tracer_works(
        self, mock_llm, mock_embedding, mock_vector_store
    ):
        """RAGEngine works fine with no tracer (default)."""
        from src.application.services.rag_engine import RAGEngine

        engine = RAGEngine(
            llm_provider=mock_llm,
            embedding_provider=mock_embedding,
            vector_store=mock_vector_store,
        )
        result = await engine.query("What is RAG?")
        assert result is not None
        assert "answer" in result
