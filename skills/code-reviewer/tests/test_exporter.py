"""
Tests for _telemetry/exporter.py

Covers: safe_flush(), _append_error()
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from _telemetry.exporter import _append_error, safe_flush


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def error_log(tmp_path: Path) -> Path:
    return tmp_path / "logs" / "telemetry.err"


@pytest.fixture
def mock_provider() -> MagicMock:
    provider = MagicMock()
    provider.force_flush.return_value = True
    return provider


# ── safe_flush() — happy path ─────────────────────────────────────────────────

def test_safe_flush_success_writes_no_error_log(
    mock_provider: MagicMock, error_log: Path
) -> None:
    safe_flush(mock_provider, str(error_log))
    assert not error_log.exists()


def test_safe_flush_calls_force_flush_with_timeout(
    mock_provider: MagicMock, error_log: Path
) -> None:
    safe_flush(mock_provider, str(error_log))
    mock_provider.force_flush.assert_called_once_with(timeout_millis=5000)


# ── safe_flush() — failure paths ─────────────────────────────────────────────

def test_safe_flush_false_return_writes_error_log(
    mock_provider: MagicMock, error_log: Path
) -> None:
    mock_provider.force_flush.return_value = False
    safe_flush(mock_provider, str(error_log))
    assert error_log.exists()
    content = error_log.read_text()
    assert "FLUSH_ERROR" in content


def test_safe_flush_exception_writes_error_log(
    mock_provider: MagicMock, error_log: Path
) -> None:
    mock_provider.force_flush.side_effect = RuntimeError("connection refused")
    safe_flush(mock_provider, str(error_log))
    assert error_log.exists()
    content = error_log.read_text()
    assert "FLUSH_ERROR" in content
    assert "connection refused" in content


def test_safe_flush_never_raises(mock_provider: MagicMock, error_log: Path) -> None:
    mock_provider.force_flush.side_effect = Exception("catastrophic failure")
    # Must not propagate
    safe_flush(mock_provider, str(error_log))


# ── _append_error() — happy path + edge cases ────────────────────────────────

def test_append_error_creates_missing_dirs(tmp_path: Path) -> None:
    log_path = tmp_path / "deep" / "nested" / "dir" / "errors.log"
    _append_error(str(log_path), "FLUSH_ERROR: test")
    assert log_path.exists()


def test_append_error_format_has_timestamp_and_message(tmp_path: Path) -> None:
    log_path = tmp_path / "test.err"
    _append_error(str(log_path), "FLUSH_ERROR: something broke")
    content = log_path.read_text()
    # Format: [YYYY-MM-DD HH:MM:SS] FLUSH_ERROR: something broke
    assert content.startswith("[20")
    assert "FLUSH_ERROR: something broke" in content


def test_append_error_appends_not_overwrites(tmp_path: Path) -> None:
    log_path = tmp_path / "test.err"
    _append_error(str(log_path), "FLUSH_ERROR: first")
    _append_error(str(log_path), "FLUSH_ERROR: second")
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert "first" in lines[0]
    assert "second" in lines[1]


def test_append_error_expands_tilde(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Redirect home to tmp_path so we don't write to real ~
    monkeypatch.setenv("HOME", str(tmp_path))
    log_path = "~/.jpmc-skills/telemetry.err"
    _append_error(log_path, "FLUSH_ERROR: tilde test")
    resolved = tmp_path / ".jpmc-skills" / "telemetry.err"
    assert resolved.exists()


def test_append_error_never_raises_on_bad_path() -> None:
    # Should not raise even if path is completely invalid
    _append_error("/dev/null/impossible/path/file.err", "FLUSH_ERROR: test")
