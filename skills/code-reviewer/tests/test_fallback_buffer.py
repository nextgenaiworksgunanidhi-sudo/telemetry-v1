"""
test_fallback_buffer.py — Tests for _telemetry/fallback_buffer.py
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from _telemetry import fallback_buffer


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_config(tmp_path: Path) -> dict:
    return {
        "endpoint": "http://localhost:4318",
        "error_log_path": str(tmp_path / "telemetry.err"),
        "fallback": {
            "enabled": True,
            "buffer_path": str(tmp_path / "pending_traces.jsonl"),
            "max_retries": 5,
        },
    }


@pytest.fixture
def sample_span() -> dict:
    return {
        "span_name": "skill.completion",
        "trace_id": "aabbccdd00112233aabbccdd00112233",
        "span_id": "aabbccdd00112233",
        "attributes": {"skill.name": "code-reviewer", "skill.outcome": "success"},
    }


# ── Test 1: buffer_span writes a valid JSONL line ─────────────────────────────

def test_buffer_span_writes_jsonl(tmp_config: dict, sample_span: dict) -> None:
    fallback_buffer.buffer_span(sample_span, tmp_config)

    buf = Path(tmp_config["fallback"]["buffer_path"])
    assert buf.exists(), "Buffer file was not created"

    line = buf.read_text(encoding="utf-8").strip()
    entry = json.loads(line)

    assert entry["span_name"] == sample_span["span_name"]
    assert entry["trace_id"] == sample_span["trace_id"]
    assert entry["span_id"] == sample_span["span_id"]
    assert entry["attributes"] == sample_span["attributes"]
    assert entry["attempt"] == 1
    assert "first_failed_at" in entry
    assert "last_attempted_at" in entry


# ── Test 2: flush_pending exports and clears buffer when endpoint reachable ───

def test_flush_pending_success_clears_buffer(
    tmp_config: dict, sample_span: dict
) -> None:
    fallback_buffer.buffer_span(sample_span, tmp_config)

    buf = Path(tmp_config["fallback"]["buffer_path"])
    assert buf.exists()

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MagicMock()
        result = fallback_buffer.flush_pending(tmp_config)

    assert result["flushed"] == 1
    assert result["failed"] == 0
    assert result["dropped"] == 0
    assert not buf.exists(), "Buffer file should be deleted after full flush"


# ── Test 3: flush_pending increments attempt count on export failure ──────────

def test_flush_pending_increments_attempt_on_failure(
    tmp_config: dict, sample_span: dict
) -> None:
    fallback_buffer.buffer_span(sample_span, tmp_config)

    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        result = fallback_buffer.flush_pending(tmp_config)

    assert result["failed"] == 1
    assert result["flushed"] == 0
    assert result["dropped"] == 0

    buf = Path(tmp_config["fallback"]["buffer_path"])
    entry = json.loads(buf.read_text(encoding="utf-8").strip())
    assert entry["attempt"] == 2


# ── Test 4: flush_pending drops trace and logs when attempt >= max_retries ────

def test_flush_pending_drops_after_max_retries(
    tmp_config: dict, sample_span: dict
) -> None:
    # Write an entry already at max_retries attempts
    buf = Path(tmp_config["fallback"]["buffer_path"])
    entry = {
        "attempt": 5,
        "first_failed_at": "2026-01-01T00:00:00+00:00",
        "last_attempted_at": "2026-01-01T00:00:00+00:00",
        "span_name": sample_span["span_name"],
        "trace_id": sample_span["trace_id"],
        "span_id": sample_span["span_id"],
        "attributes": sample_span["attributes"],
    }
    buf.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        result = fallback_buffer.flush_pending(tmp_config)

    assert result["dropped"] == 1
    assert result["flushed"] == 0
    assert result["failed"] == 0

    err_log = Path(tmp_config["error_log_path"])
    assert err_log.exists(), "Error log should be written on drop"
    content = err_log.read_text(encoding="utf-8")
    assert "DROPPED" in content
    assert sample_span["trace_id"] in content


# ── Test 5: flush_pending returns correct summary in all cases ────────────────

def test_flush_pending_summary_mixed(tmp_config: dict) -> None:
    buf = Path(tmp_config["fallback"]["buffer_path"])
    entries = [
        # Will succeed on export
        {"attempt": 1, "first_failed_at": "2026-01-01T00:00:00+00:00",
         "last_attempted_at": "2026-01-01T00:00:00+00:00",
         "span_name": "s1", "trace_id": "a" * 32, "span_id": "b" * 16,
         "attributes": {}},
        # Will fail but not yet at max_retries
        {"attempt": 3, "first_failed_at": "2026-01-01T00:00:00+00:00",
         "last_attempted_at": "2026-01-01T00:00:00+00:00",
         "span_name": "s2", "trace_id": "c" * 32, "span_id": "d" * 16,
         "attributes": {}},
        # Will be dropped (at max_retries)
        {"attempt": 5, "first_failed_at": "2026-01-01T00:00:00+00:00",
         "last_attempted_at": "2026-01-01T00:00:00+00:00",
         "span_name": "s3", "trace_id": "e" * 32, "span_id": "f" * 16,
         "attributes": {}},
    ]
    buf.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")

    call_count = 0

    def selective_urlopen(req, timeout=3):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MagicMock()           # first entry succeeds
        raise OSError("connection refused")  # remaining fail

    with patch("urllib.request.urlopen", side_effect=selective_urlopen):
        result = fallback_buffer.flush_pending(tmp_config)

    assert result["flushed"] == 1
    assert result["failed"] == 1
    assert result["dropped"] == 1


# ── Test 6: fallback disabled — buffer_span does nothing ─────────────────────

def test_buffer_span_disabled(tmp_path: Path, sample_span: dict) -> None:
    config = {
        "endpoint": "http://localhost:4318",
        "error_log_path": str(tmp_path / "telemetry.err"),
        "fallback": {
            "enabled": False,
            "buffer_path": str(tmp_path / "pending_traces.jsonl"),
            "max_retries": 5,
        },
    }
    fallback_buffer.buffer_span(sample_span, config)

    buf = Path(config["fallback"]["buffer_path"])
    assert not buf.exists(), "Buffer file must not be created when fallback is disabled"


def test_flush_pending_disabled(tmp_path: Path, sample_span: dict) -> None:
    config = {
        "endpoint": "http://localhost:4318",
        "error_log_path": str(tmp_path / "telemetry.err"),
        "fallback": {
            "enabled": False,
            "buffer_path": str(tmp_path / "pending_traces.jsonl"),
            "max_retries": 5,
        },
    }
    result = fallback_buffer.flush_pending(config)
    assert result == {"flushed": 0, "failed": 0, "dropped": 0}


# ── Test 7: malformed JSONL line is skipped without crashing ─────────────────

def test_flush_pending_skips_malformed_lines(
    tmp_config: dict, sample_span: dict
) -> None:
    buf = Path(tmp_config["fallback"]["buffer_path"])
    good_entry = {
        "attempt": 1, "first_failed_at": "2026-01-01T00:00:00+00:00",
        "last_attempted_at": "2026-01-01T00:00:00+00:00",
        "span_name": sample_span["span_name"],
        "trace_id": sample_span["trace_id"],
        "span_id": sample_span["span_id"],
        "attributes": sample_span["attributes"],
    }
    buf.write_text(
        "THIS IS NOT JSON\n" + json.dumps(good_entry) + "\n",
        encoding="utf-8",
    )

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MagicMock()
        result = fallback_buffer.flush_pending(tmp_config)

    # Malformed line skipped, good entry flushed
    assert result["flushed"] == 1
    assert result["failed"] == 0
    assert result["dropped"] == 0
