"""OpenTelemetry-based tracing wrapper for the RAG pipeline.

The wrapper is dependency-optional: if OpenTelemetry is not installed
or ENABLE_TRACING is False, a no-op tracer is used so the application
never breaks because of tracing.
"""

import logging
from contextlib import contextmanager

from src.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)


class NoopSpan:
    """Span that does nothing."""

    def set_attribute(self, key: str, value: object) -> None:
        pass

    def add_event(self, name: str, attributes: dict | None = None) -> None:
        pass

    def end(self) -> None:
        pass


class NoopTracer:
    """Tracer that creates no-op spans (safe drop-in)."""

    @contextmanager
    def start_as_current_span(self, name: str, attributes: dict | None = None):
        yield NoopSpan()

    @contextmanager
    def start_span(self, name: str):
        yield NoopSpan()


def _create_opentelemetry_tracer() -> object:
    """Create a real OpenTelemetry tracer exporting to Phoenix.

    Returns None (and logs) if dependencies are unavailable.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        settings = get_settings()
        resource = Resource.create({"service.name": settings.TRACING_SERVICE_NAME})
        provider = TracerProvider(resource=resource)
        # NOTE: ``insecure`` is a gRPC-exporter-only kwarg; the HTTP exporter
        # already implies it for http:// endpoints and would raise TypeError.
        exporter = OTLPSpanExporter(endpoint=settings.TRACING_ENDPOINT)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        tracer = trace.get_tracer("qa-assistant")
        logger.info(
            "OpenTelemetry tracer initialized (endpoint=%s)",
            settings.TRACING_ENDPOINT,
        )
        return tracer
    except Exception as exc:
        logger.warning("Failed to initialize OpenTelemetry tracer: %s", exc)
        return None


def create_tracer() -> object | None:
    """Create a tracer based on settings. Never raises.

    Returns None when disabled, a no-op tracer when enabled but deps
    are missing, or a real tracer when fully available.
    """
    settings = get_settings()
    if not getattr(settings, "ENABLE_TRACING", False):
        return None

    tracer = _create_opentelemetry_tracer()
    if tracer is None:
        logger.warning("Tracing enabled but unavailable; using no-op tracer")
        return NoopTracer()
    return tracer
