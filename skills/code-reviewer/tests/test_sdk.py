"""
Tests for _telemetry/sdk.py

Covers: start_skill_span(), end_skill_span()
Uses InMemorySpanExporter to avoid real network calls.
"""

import sys
from pathlib import Path
from typing import Generator

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

sys.path.insert(0, str(Path(__file__).parent.parent))
from _telemetry import sdk


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def base_config() -> dict:
    return {
        "skill_id": "jpmc.test.skill",
        "skill_version": "1.2.3",
        "endpoint": "http://localhost:4318",
        "flush_interval_ms": 100,
        "batch_size": 5,
    }


@pytest.fixture
def in_memory_exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture(autouse=True)
def patch_otlp_exporter(in_memory_exporter: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Replace OTLPSpanExporter and BatchSpanProcessor in sdk.py's own namespace.
    sdk.py does `from ... import X`, so we must patch where sdk.py holds the name.
    """
    monkeypatch.setattr(sdk, "OTLPSpanExporter", lambda **kwargs: in_memory_exporter)
    monkeypatch.setattr(sdk, "BatchSpanProcessor", lambda exporter, **kwargs: SimpleSpanProcessor(exporter))


# ── start_skill_span() ────────────────────────────────────────────────────────

def test_start_skill_span_returns_provider_and_span(
    base_config: dict,
) -> None:
    provider, span = sdk.start_skill_span(base_config, {})
    assert isinstance(provider, TracerProvider)
    assert span is not None
    provider.shutdown()


def test_start_skill_span_span_context_is_valid(base_config: dict) -> None:
    provider, span = sdk.start_skill_span(base_config, {})
    ctx = span.get_span_context()
    assert ctx.trace_id != 0
    assert ctx.span_id != 0
    provider.shutdown()


def test_start_skill_span_extra_attrs_set_on_span(
    base_config: dict, in_memory_exporter: InMemorySpanExporter
) -> None:
    extra = {"invoke.timestamp": "2026-01-01T00:00:00", "skill.name": "test-skill"}
    provider, span = sdk.start_skill_span(base_config, extra)
    span.end()
    provider.force_flush(timeout_millis=1000)
    provider.shutdown()
    spans = in_memory_exporter.get_finished_spans()
    assert len(spans) == 1
    attrs = spans[0].attributes
    assert attrs.get("invoke.timestamp") == "2026-01-01T00:00:00"
    assert attrs.get("skill.name") == "test-skill"


def test_start_skill_span_resource_has_skill_id(base_config: dict) -> None:
    provider, span = sdk.start_skill_span(base_config, {})
    resource_attrs = provider.resource.attributes
    assert resource_attrs.get("skill.id") == "jpmc.test.skill"
    assert resource_attrs.get("skill.version") == "1.2.3"
    provider.shutdown()


def test_start_skill_span_resource_attrs_merged(base_config: dict) -> None:
    extra = {"_resource_attrs": {"host.os": "darwin", "ide.type": "vscode"}}
    provider, span = sdk.start_skill_span(base_config, extra)
    resource_attrs = provider.resource.attributes
    assert resource_attrs.get("host.os") == "darwin"
    provider.shutdown()


# ── end_skill_span() ──────────────────────────────────────────────────────────

def test_end_skill_span_success_sets_ok_status(
    base_config: dict, in_memory_exporter: InMemorySpanExporter
) -> None:
    provider, span = sdk.start_skill_span(base_config, {})
    sdk.end_skill_span(span, provider, "success")
    spans = in_memory_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code == StatusCode.OK
    assert spans[0].attributes.get("skill.outcome") == "success"


def test_end_skill_span_error_sets_error_status(
    base_config: dict, in_memory_exporter: InMemorySpanExporter
) -> None:
    provider, span = sdk.start_skill_span(base_config, {})
    sdk.end_skill_span(span, provider, "error", error_message="upstream timeout")
    spans = in_memory_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code == StatusCode.ERROR
    assert spans[0].attributes.get("skill.outcome") == "error"


def test_end_skill_span_error_records_exception(
    base_config: dict, in_memory_exporter: InMemorySpanExporter
) -> None:
    provider, span = sdk.start_skill_span(base_config, {})
    sdk.end_skill_span(span, provider, "error", error_message="db connection failed")
    spans = in_memory_exporter.get_finished_spans()
    events = spans[0].events
    assert any(e.name == "exception" for e in events)


def test_end_skill_span_no_error_message_sets_ok(
    base_config: dict, in_memory_exporter: InMemorySpanExporter
) -> None:
    provider, span = sdk.start_skill_span(base_config, {})
    sdk.end_skill_span(span, provider, "success", error_message=None)
    spans = in_memory_exporter.get_finished_spans()
    assert spans[0].status.status_code == StatusCode.OK
