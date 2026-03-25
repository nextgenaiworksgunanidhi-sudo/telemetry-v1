"""
exporter.py — Safe flush wrapper for the OTel TracerProvider.
Never raises — all errors are written to the configured error log file.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from opentelemetry.sdk.trace import TracerProvider


def safe_flush(tracer_provider: TracerProvider, error_log_path: str) -> None:
    """
    Attempt force_flush on the provider. On False return (timeout/failure)
    or any exception, write a timestamped error line to error_log_path.
    Never raises.
    """
    try:
        success = tracer_provider.force_flush(timeout_millis=5000)
        if not success:
            _append_error(error_log_path, "FLUSH_ERROR: force_flush returned False (timeout or export failure)")
    except Exception as exc:
        _append_error(error_log_path, f"FLUSH_ERROR: {exc}")


def _append_error(log_path: str, message: str) -> None:
    """Append a timestamped error line to log_path, creating dirs as needed."""
    try:
        resolved = Path(log_path).expanduser()
        os.makedirs(resolved.parent, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with open(resolved, "a") as fh:
            fh.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass
