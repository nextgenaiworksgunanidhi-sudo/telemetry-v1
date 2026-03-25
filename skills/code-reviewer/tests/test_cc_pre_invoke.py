"""
Tests for hooks/pre-invoke.py

Covers: main() dispatch logic — skill detection, prompt caching,
OTel span opening, and silent handling of bad input.
"""

import importlib.util
import json
import sys
from io import StringIO
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

# Load pre-invoke as a module (hyphen-free filename now)
_HOOKS_DIR = Path(__file__).parent.parent / "scripts" / "hooks"
_SPEC = importlib.util.spec_from_file_location(
    "pre_invoke", _HOOKS_DIR / "pre-invoke.py"
)
pre_invoke = importlib.util.module_from_spec(_SPEC)  # type: ignore[arg-type]
_SPEC.loader.exec_module(pre_invoke)  # type: ignore[union-attr]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_temp_files() -> Generator[None, None, None]:
    """Remove temp files before and after each test."""
    pre_invoke._PROMPT_CACHE.unlink(missing_ok=True)
    pre_invoke._SPAN_CTX_FILE.unlink(missing_ok=True)
    yield
    pre_invoke._PROMPT_CACHE.unlink(missing_ok=True)
    pre_invoke._SPAN_CTX_FILE.unlink(missing_ok=True)


def _stdin(data: dict) -> StringIO:
    return StringIO(json.dumps(data))


# ── Happy path: skill prompt triggers span open ───────────────────────────────

def test_skill_prompt_caches_raw_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", _stdin({"prompt": "/code-reviewer review auth.py"}))
    with patch.object(pre_invoke, "_open_span"):
        pre_invoke.main()
    assert pre_invoke._PROMPT_CACHE.read_text() == "/code-reviewer review auth.py"


def test_skill_prompt_calls_open_span(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", _stdin({"prompt": "/code-reviewer check my code"}))
    mock_open_span = MagicMock()
    with patch.object(pre_invoke, "_open_span", mock_open_span):
        with patch("builtins.open", MagicMock(return_value=MagicMock(
            __enter__=MagicMock(return_value=MagicMock()), __exit__=MagicMock(return_value=False)))):
            with patch("yaml.safe_load", return_value={}):
                pre_invoke.main()
    mock_open_span.assert_called_once()


# ── All non-empty prompts now trigger telemetry (FIX 1 — no prefix filter) ───

def test_non_skill_prompt_writes_prompt_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", _stdin({"prompt": "what is Python?"}))
    with patch.object(pre_invoke, "_open_span"):
        pre_invoke.main()
    assert pre_invoke._PROMPT_CACHE.exists()


def test_non_skill_prompt_calls_open_span(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", _stdin({"prompt": "just a normal question"}))
    mock_open_span = MagicMock()
    with patch.object(pre_invoke, "_open_span", mock_open_span):
        with patch("builtins.open", MagicMock(return_value=MagicMock(
            __enter__=MagicMock(return_value=MagicMock()), __exit__=MagicMock(return_value=False)))):
            with patch("yaml.safe_load", return_value={}):
                pre_invoke.main()
    mock_open_span.assert_called_once()


def test_empty_prompt_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", _stdin({"prompt": ""}))
    mock_open_span = MagicMock()
    with patch.object(pre_invoke, "_open_span", mock_open_span):
        pre_invoke.main()
    mock_open_span.assert_not_called()


# ── Edge cases: bad stdin ─────────────────────────────────────────────────────

def test_invalid_json_stdin_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("NOT JSON {{{"))
    pre_invoke.main()  # must not raise


def test_missing_prompt_key_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", _stdin({"hook_event_name": "UserPromptSubmit"}))
    pre_invoke.main()  # must not raise


# ── _read_prompt unit tests ───────────────────────────────────────────────────

def test_read_prompt_returns_prompt_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", _stdin({"prompt": "/code-reviewer hello"}))
    assert pre_invoke._read_prompt() == "/code-reviewer hello"


def test_read_prompt_returns_empty_on_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("BAD"))
    assert pre_invoke._read_prompt() == ""


def test_read_prompt_returns_empty_on_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", _stdin({"other": "value"}))
    assert pre_invoke._read_prompt() == ""
