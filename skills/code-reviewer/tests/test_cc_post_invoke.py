"""
Tests for hooks/post-invoke.py

Covers: main() dispatch logic — gate on span ctx, stdin reading,
prompt cache cleanup, and silent failure handling.
"""

import importlib.util
import json
import sys
from io import StringIO
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

# Load post-invoke as a module
_HOOKS_DIR = Path(__file__).parent.parent / "scripts" / "hooks"
_SPEC = importlib.util.spec_from_file_location(
    "post_invoke", _HOOKS_DIR / "post-invoke.py"
)
post_invoke = importlib.util.module_from_spec(_SPEC)  # type: ignore[arg-type]
_SPEC.loader.exec_module(post_invoke)  # type: ignore[union-attr]

_SPAN_CTX = post_invoke._SPAN_CTX_FILE
_PROMPT_CACHE = post_invoke._PROMPT_CACHE


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_temp_files() -> Generator[None, None, None]:
    """Ensure temp files are absent before and after every test."""
    _SPAN_CTX.unlink(missing_ok=True)
    _PROMPT_CACHE.unlink(missing_ok=True)
    yield
    _SPAN_CTX.unlink(missing_ok=True)
    _PROMPT_CACHE.unlink(missing_ok=True)


@pytest.fixture
def span_ctx() -> Generator[None, None, None]:
    """Write a minimal span context file so the gate passes."""
    _SPAN_CTX.write_text(
        json.dumps({
            "trace_id": "abcd1234" * 8,
            "span_id": "ef567890" * 4,
            "start_time_iso": "2026-01-01T00:00:00+00:00",
            "telemetry_yaml_path": "/dev/null",
        })
    )
    yield
    _SPAN_CTX.unlink(missing_ok=True)


def _stdin(data: dict) -> StringIO:
    return StringIO(json.dumps(data))


def _stop_event(message: str = "LLM response here") -> dict:
    return {
        "hook_event_name": "Stop",
        "session_id": "test-session",
        "stop_hook_active": False,
        "last_assistant_message": message,
    }


# ── Gate: no span ctx → no-op ─────────────────────────────────────────────────

def test_no_span_ctx_returns_early(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", _stdin(_stop_event()))
    mock_build = MagicMock()
    with patch.object(post_invoke, "_build_provider", mock_build):
        post_invoke.main()
    mock_build.assert_not_called()


# ── _read_stop_event unit tests ───────────────────────────────────────────────

def test_read_stop_event_returns_last_assistant_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    msg = "Found a SQL injection vulnerability."
    monkeypatch.setattr("sys.stdin", _stdin(_stop_event(message=msg)))
    assert post_invoke._read_stop_event() == msg


def test_read_stop_event_returns_empty_on_bad_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("INVALID JSON"))
    assert post_invoke._read_stop_event() == ""


def test_read_stop_event_returns_empty_on_missing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", _stdin({"hook_event_name": "Stop"}))
    assert post_invoke._read_stop_event() == ""


# ── _read_prompt_cache unit tests ────────────────────────────────────────────

def test_read_prompt_cache_returns_contents() -> None:
    _PROMPT_CACHE.write_text("/code-reviewer check auth.py")
    assert post_invoke._read_prompt_cache() == "/code-reviewer check auth.py"


def test_read_prompt_cache_deletes_file_after_read() -> None:
    _PROMPT_CACHE.write_text("/code-reviewer test")
    post_invoke._read_prompt_cache()
    assert not _PROMPT_CACHE.exists()


def test_read_prompt_cache_returns_empty_when_absent() -> None:
    assert post_invoke._read_prompt_cache() == ""


def test_read_prompt_cache_deletes_file_even_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _PROMPT_CACHE.write_text("prompt")
    monkeypatch.setattr(
        "pathlib.Path.read_text", MagicMock(side_effect=OSError("fail"))
    )
    result = post_invoke._read_prompt_cache()
    assert result == ""
    assert not _PROMPT_CACHE.exists()


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_invalid_json_stdin_no_span_ctx_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No span_ctx fixture — main() exits at the gate before any OTel work.
    monkeypatch.setattr("sys.stdin", StringIO("INVALID JSON"))
    post_invoke.main()  # must not raise
