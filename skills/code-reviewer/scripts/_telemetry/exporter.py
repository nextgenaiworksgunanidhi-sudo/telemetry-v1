"""
exporter.py — Safe flush wrapper for the OTel TracerProvider.
Never raises — all errors are written to the configured error log file.

Also provides ExportTracker and TrackingExporter so callers can detect
whether the underlying OTLP exporter actually succeeded, since
force_flush() returns True even when all export retries are exhausted.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from _telemetry import fallback_buffer


class ExportTracker:
    """Mutable flag set to True the first time an export fails."""
    def __init__(self) -> None:
        self.last_failed: bool = False


class TrackingExporter(SpanExporter):
    """Wraps any SpanExporter and records export failures in ExportTracker."""

    def __init__(self, delegate: SpanExporter, tracker: ExportTracker) -> None:
        self.delegate = delegate
        self.tracker = tracker

    def export(self, spans: Sequence) -> SpanExportResult:
        result = self.delegate.export(spans)
        if result != SpanExportResult.SUCCESS:
            self.tracker.last_failed = True
        return result

    def shutdown(self) -> None:
        self.delegate.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.delegate.force_flush(timeout_millis)


def safe_flush(
    tracer_provider: TracerProvider,
    error_log_path: str,
    span_data: dict = None,
    config: dict = None,
    tracker: ExportTracker = None,
) -> None:
    """
    Attempt force_flush on the provider. Detects failure via tracker
    (preferred) or force_flush False return or exception. On failure,
    buffers the span locally if span_data and config are provided.
    Never raises.
    """
    export_failed = False
    try:
        success = tracer_provider.force_flush(timeout_millis=5000)
        if not success:
            export_failed = True
            _append_error(
                error_log_path,
                "FLUSH_ERROR: force_flush returned False (timeout or export failure)",
            )
    except Exception as exc:
        export_failed = True
        _append_error(error_log_path, f"FLUSH_ERROR: {exc}")

    # force_flush returns True even when all OTel retries are exhausted;
    # check the tracker for the reliable failure signal.
    if tracker is not None and tracker.last_failed:
        export_failed = True

    if export_failed:
        if span_data is not None and config is not None:
            fallback_buffer.buffer_span(span_data, config)
            sys.stderr.write("[exporter] Export failed — span buffered for retry\n")
        else:
            _append_error(error_log_path, "FLUSH_ERROR: no span_data/config for buffering")


def _append_error(log_path: str, message: str) -> None:
    """Append a timestamped error line to log_path, creating dirs as needed."""
    try:
        resolved = Path(log_path).expanduser()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with open(resolved, "a") as fh:
            fh.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass
