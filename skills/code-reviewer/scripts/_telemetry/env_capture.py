"""
env_capture.py — Collects host/runtime resource attributes for OTel spans.
All attributes are safe to export: hostname is hashed, never raw.
"""

import hashlib
import os
import platform
import socket
import sys
from typing import Optional


def _detect_ide() -> str:
    """Detect the IDE/agent context from environment variables."""
    if os.environ.get("VSCODE_PID"):
        return "vscode"
    if os.environ.get("CLAUDE_CODE"):
        return "claude-code"
    if os.environ.get("TERM_PROGRAM") == "vscode":
        return "vscode"
    return "unknown"


def _hash_hostname() -> str:
    """Return sha256 hex digest of the hostname — never expose raw hostname."""
    try:
        raw = socket.gethostname()
        return hashlib.sha256(raw.encode()).hexdigest()
    except OSError:
        return hashlib.sha256(b"unknown").hexdigest()


def get_resource_attributes() -> dict:
    """
    Return a dict of resource-level OTel attributes describing the
    host and runtime environment. Safe to attach to any span or resource.
    """
    return {
        "host.os": sys.platform,
        "host.id": _hash_hostname(),
        "ide.type": _detect_ide(),
        "runtime.python_version": sys.version,
        "runtime.platform": platform.platform(),
    }


if __name__ == "__main__":
    attrs = get_resource_attributes()
    for key, value in attrs.items():
        print(f"  {key}: {value}")
