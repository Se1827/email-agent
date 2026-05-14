"""OpenTelemetry setup and tracing helpers."""

from __future__ import annotations

import logging
from contextlib import nullcontext
from typing import Any

log = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
except Exception:  # pragma: no cover - dependency may be absent in lean installs.
    trace = None  # type: ignore[assignment]
    OTLPSpanExporter = None  # type: ignore[assignment]
    FastAPIInstrumentor = None  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment]
    BatchSpanProcessor = None  # type: ignore[assignment]
    ConsoleSpanExporter = None  # type: ignore[assignment]


def setup_telemetry(app: Any, settings: Any) -> None:
    """Configure OpenTelemetry for FastAPI and local spans when enabled."""
    if not getattr(settings, "otel_enabled", False):
        return
    if trace is None or TracerProvider is None or BatchSpanProcessor is None:
        log.warning("otel_unavailable", extra={"otel_enabled": True})
        return

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    exporter = (
        OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        if settings.otel_exporter_otlp_endpoint and OTLPSpanExporter is not None
        else ConsoleSpanExporter()
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    if FastAPIInstrumentor is not None:
        FastAPIInstrumentor.instrument_app(app)

    log.info(
        "otel_configured",
        extra={
            "otel_enabled": True,
            "otel_service_name": settings.otel_service_name,
            "otel_exporter": "otlp" if settings.otel_exporter_otlp_endpoint else "console",
        },
    )


def span(name: str, **attributes: Any):
    """Return a span context manager, or a no-op when OTEL is unavailable."""
    if trace is None:
        return nullcontext()
    tracer = trace.get_tracer("email-agent")
    manager = tracer.start_as_current_span(name)
    active_span = manager.__enter__()
    for key, value in attributes.items():
        if value is not None:
            active_span.set_attribute(key, value)
    return _SpanContext(manager)


def current_trace_context() -> dict[str, str]:
    """Return current trace/span IDs for structured logs."""
    if trace is None:
        return {}
    active_span = trace.get_current_span()
    context = active_span.get_span_context()
    if not context or not context.is_valid:
        return {}
    return {
        "trace_id": f"{context.trace_id:032x}",
        "span_id": f"{context.span_id:016x}",
    }


class _SpanContext:
    def __init__(self, manager: Any) -> None:
        self._manager = manager

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._manager.__exit__(exc_type, exc, tb)
