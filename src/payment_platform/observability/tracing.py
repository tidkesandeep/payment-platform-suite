"""OpenTelemetry traces for /v1/payments. No cloud exporter required."""

from __future__ import annotations

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer, get_tracer


def make_tracer(*, service_name: str = "payment-platform") -> Tracer:
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    return get_tracer("payment_platform.authorize", tracer_provider=provider)


def make_memory_tracer(
    *, service_name: str = "payment-platform"
) -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return get_tracer("payment_platform.authorize", tracer_provider=provider), exporter
