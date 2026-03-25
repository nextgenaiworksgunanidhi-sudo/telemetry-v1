"""
sdk.py — Initialises the OTel TracerProvider and manages root skill spans.
Provides start_skill_span() and end_skill_span() as the sole public API.
"""

from typing import Optional, Tuple

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import StatusCode


def start_skill_span(
    telemetry_config: dict,
    extra_attrs: dict,
) -> Tuple[TracerProvider, trace.Span]:
    """
    Build a TracerProvider with OTLP HTTP exporter, start a root
    'skill.invoke' span, attach extra_attrs, and return both objects.
    Caller must keep both alive until end_skill_span() is called.
    """
    skill_id = telemetry_config.get("skill_id", "unknown")
    skill_version = telemetry_config.get("skill_version", "0.0.0")
    endpoint = telemetry_config.get("endpoint", "http://localhost:4318")
    flush_interval_ms = int(telemetry_config.get("flush_interval_ms", 3000))
    batch_size = int(telemetry_config.get("batch_size", 20))

    resource_attrs = {
        "skill.id": skill_id,
        "skill.version": skill_version,
        "service.name": skill_id,
    }
    resource_attrs.update(extra_attrs.pop("_resource_attrs", {}))

    resource = Resource.create(resource_attrs)

    exporter = OTLPSpanExporter(
        endpoint=f"{endpoint.rstrip('/')}/v1/traces",
    )

    processor = BatchSpanProcessor(
        exporter,
        max_export_batch_size=batch_size,
        schedule_delay_millis=flush_interval_ms,
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    tracer = provider.get_tracer(skill_id)
    span = tracer.start_span("skill.invoke")

    for key, value in extra_attrs.items():
        span.set_attribute(key, value)

    return provider, span


def end_skill_span(
    span: trace.Span,
    tracer_provider: TracerProvider,
    outcome: str,
    error_message: Optional[str] = None,
) -> None:
    """
    Finalise the span: set outcome, record errors if any,
    set OTel status, then force_flush and shutdown the provider.
    """
    span.set_attribute("skill.outcome", outcome)

    if error_message:
        span.record_exception(Exception(error_message))
        span.set_status(StatusCode.ERROR, error_message)
    else:
        span.set_status(StatusCode.OK)

    span.end()
    tracer_provider.force_flush(timeout_millis=5000)
    tracer_provider.shutdown()
