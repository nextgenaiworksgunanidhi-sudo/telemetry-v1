"""
Tests for _telemetry/env_capture.py

Covers: get_resource_attributes(), _detect_ide(), _hash_hostname()
"""

import socket
import sys
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from _telemetry.env_capture import _detect_ide, _hash_hostname, get_resource_attributes


# ── get_resource_attributes() — happy path ────────────────────────────────────

def test_get_resource_attributes_returns_all_keys() -> None:
    attrs = get_resource_attributes()
    required = {"host.os", "host.id", "ide.type", "runtime.python_version", "runtime.platform"}
    assert required.issubset(attrs.keys())


def test_host_id_is_64_char_hex() -> None:
    attrs = get_resource_attributes()
    host_id = attrs["host.id"]
    assert len(host_id) == 64
    assert all(c in "0123456789abcdef" for c in host_id)


def test_host_id_is_not_raw_hostname() -> None:
    raw_hostname = socket.gethostname()
    attrs = get_resource_attributes()
    assert attrs["host.id"] != raw_hostname


def test_host_os_matches_sys_platform() -> None:
    attrs = get_resource_attributes()
    assert attrs["host.os"] == sys.platform


def test_runtime_python_version_is_string() -> None:
    attrs = get_resource_attributes()
    assert isinstance(attrs["runtime.python_version"], str)
    assert len(attrs["runtime.python_version"]) > 0


def test_runtime_platform_is_string() -> None:
    attrs = get_resource_attributes()
    assert isinstance(attrs["runtime.platform"], str)
    assert len(attrs["runtime.platform"]) > 0


# ── _detect_ide() — all branches ─────────────────────────────────────────────

def test_detect_ide_vscode_via_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VSCODE_PID", "12345")
    monkeypatch.delenv("CLAUDE_CODE", raising=False)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    assert _detect_ide() == "vscode"


def test_detect_ide_claude_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VSCODE_PID", raising=False)
    monkeypatch.setenv("CLAUDE_CODE", "1")
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    assert _detect_ide() == "claude-code"


def test_detect_ide_term_program_vscode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VSCODE_PID", raising=False)
    monkeypatch.delenv("CLAUDE_CODE", raising=False)
    monkeypatch.setenv("TERM_PROGRAM", "vscode")
    assert _detect_ide() == "vscode"


def test_detect_ide_unknown_when_no_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VSCODE_PID", raising=False)
    monkeypatch.delenv("CLAUDE_CODE", raising=False)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    assert _detect_ide() == "unknown"


def test_detect_ide_vscode_pid_takes_priority_over_claude_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VSCODE_PID", "1")
    monkeypatch.setenv("CLAUDE_CODE", "1")
    assert _detect_ide() == "vscode"


# ── _hash_hostname() — happy path + failure ───────────────────────────────────

def test_hash_hostname_returns_64_char_hex() -> None:
    result = _hash_hostname()
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_hash_hostname_is_deterministic() -> None:
    assert _hash_hostname() == _hash_hostname()


def test_hash_hostname_falls_back_on_oserror() -> None:
    with patch("socket.gethostname", side_effect=OSError("no hostname")):
        result = _hash_hostname()
    # Should return sha256("unknown") — still a valid 64-char hex
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)
