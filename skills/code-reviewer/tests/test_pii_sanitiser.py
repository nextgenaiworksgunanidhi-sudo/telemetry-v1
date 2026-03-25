"""
Tests for _telemetry/pii_sanitiser.py

Covers: sanitise(), apply_redactions()
Rules: happy path + at least one failure/edge case per function.
"""

import hashlib
import sys
from pathlib import Path
from typing import Generator

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from _telemetry.pii_sanitiser import apply_redactions, sanitise


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def full_config() -> dict:
    """Full telemetry config with all standard PII patterns."""
    return {
        "pii": {
            "prompt_max_chars": 50,
            "response_max_chars": 30,
            "redact_patterns": [
                {
                    "name": "email",
                    "pattern": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                    "replacement": "[REDACTED-EMAIL]",
                },
                {
                    "name": "jpmc_sid",
                    "pattern": r"\bSID[0-9]{6,}\b",
                    "replacement": "[REDACTED-SID]",
                },
                {
                    "name": "account_number",
                    "pattern": r"\b[0-9]{8,17}\b",
                    "replacement": "[REDACTED-ACCT]",
                },
                {
                    "name": "jwt_token",
                    "pattern": r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
                    "replacement": "[REDACTED-JWT]",
                },
                {
                    "name": "ssn",
                    "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
                    "replacement": "[REDACTED-SSN]",
                },
            ],
        }
    }


@pytest.fixture
def empty_config() -> dict:
    """Config with no PII patterns and large limits."""
    return {"pii": {"prompt_max_chars": 1000, "response_max_chars": 1000, "redact_patterns": []}}


# ── sanitise() — happy paths ──────────────────────────────────────────────────

def test_sanitise_email_redacted(full_config: dict) -> None:
    result = sanitise("Hello user@example.com here", "ok", full_config)
    assert "[REDACTED-EMAIL]" in result["prompt_preview"]
    assert "user@example.com" not in result["prompt_preview"]


def test_sanitise_jwt_redacted(full_config: dict) -> None:
    result = sanitise(
        "Token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.abc123",
        "ok",
        full_config,
    )
    assert "[REDACTED-JWT]" in result["prompt_preview"]


def test_sanitise_ssn_redacted(full_config: dict) -> None:
    result = sanitise("SSN is 123-45-6789", "ok", full_config)
    assert "[REDACTED-SSN]" in result["prompt_preview"]
    assert "123-45-6789" not in result["prompt_preview"]


def test_sanitise_sid_redacted(full_config: dict) -> None:
    result = sanitise("User SID9876543 filed a ticket", "ok", full_config)
    assert "[REDACTED-SID]" in result["prompt_preview"]


def test_sanitise_account_number_redacted(full_config: dict) -> None:
    result = sanitise("Account 123456789 needs review", "ok", full_config)
    assert "[REDACTED-ACCT]" in result["prompt_preview"]


def test_sanitise_hash_is_64_char_hex(full_config: dict) -> None:
    result = sanitise("some prompt", "some response", full_config)
    assert len(result["prompt_hash"]) == 64
    assert all(c in "0123456789abcdef" for c in result["prompt_hash"])


def test_sanitise_hash_computed_before_redaction(full_config: dict) -> None:
    """Hash must equal sha256 of the ORIGINAL raw prompt, not the redacted one."""
    raw = "Contact user@example.com for help"
    result = sanitise(raw, "ok", full_config)
    expected_hash = hashlib.sha256(raw.encode()).hexdigest()
    assert result["prompt_hash"] == expected_hash


def test_sanitise_prompt_char_count_is_original_length(full_config: dict) -> None:
    raw = "Hello user@example.com"
    result = sanitise(raw, "ok", full_config)
    assert result["prompt_char_count"] == len(raw)


def test_sanitise_prompt_truncated_to_max_chars(full_config: dict) -> None:
    long_prompt = "a" * 200
    result = sanitise(long_prompt, "ok", full_config)
    assert len(result["prompt_preview"]) <= 50


def test_sanitise_response_truncated_flag_true(full_config: dict) -> None:
    long_response = "b" * 200
    result = sanitise("prompt", long_response, full_config)
    assert result["response_truncated"] is True
    assert len(result["response_preview"]) <= 30


def test_sanitise_response_truncated_flag_false_when_short(full_config: dict) -> None:
    result = sanitise("prompt", "short", full_config)
    assert result["response_truncated"] is False


def test_sanitise_multiple_pii_types_in_one_prompt(full_config: dict) -> None:
    prompt = "user@jpmc.com SID1234567 SSN 123-45-6789"
    result = sanitise(prompt, "ok", full_config)
    assert "[REDACTED-EMAIL]" in result["prompt_preview"]
    assert "[REDACTED-SID]" in result["prompt_preview"]
    assert "[REDACTED-SSN]" in result["prompt_preview"]


def test_sanitise_response_char_count(full_config: dict) -> None:
    response = "This is 20 chars ok!"
    result = sanitise("prompt", response, full_config)
    assert result["response_char_count"] == len(response)


# ── sanitise() — edge cases ───────────────────────────────────────────────────

def test_sanitise_empty_prompt(full_config: dict) -> None:
    result = sanitise("", "response", full_config)
    assert result["prompt_preview"] == ""
    assert result["prompt_char_count"] == 0
    # sha256 of empty string — well-known value
    assert result["prompt_hash"] == hashlib.sha256(b"").hexdigest()


def test_sanitise_none_prompt_returns_safe_defaults(full_config: dict) -> None:
    result = sanitise(None, None, full_config)  # type: ignore[arg-type]
    assert result["prompt_preview"] == ""
    assert result["prompt_char_count"] == 0
    assert result["response_preview"] == ""
    assert result["response_char_count"] == 0
    assert result["response_truncated"] is False
    assert len(result["prompt_hash"]) == 64


def test_sanitise_never_raises_on_bad_config() -> None:
    result = sanitise("prompt", "response", {})
    # Should return valid dict, not raise
    assert "prompt_hash" in result
    assert "prompt_preview" in result


def test_sanitise_never_raises_on_corrupt_pattern() -> None:
    bad_config = {
        "pii": {
            "prompt_max_chars": 500,
            "response_max_chars": 300,
            "redact_patterns": [{"name": "bad", "pattern": "[invalid(regex", "replacement": "X"}],
        }
    }
    # Should not raise even with a broken regex
    result = sanitise("hello world", "response", bad_config)
    assert "prompt_hash" in result


# ── apply_redactions() — happy path + edge cases ──────────────────────────────

def test_apply_redactions_no_patterns(empty_config: dict) -> None:
    text = "nothing should change here"
    assert apply_redactions(text, empty_config) == text


def test_apply_redactions_applies_in_order(full_config: dict) -> None:
    text = "user@example.com"
    result = apply_redactions(text, full_config)
    assert "[REDACTED-EMAIL]" in result


def test_apply_redactions_returns_original_on_missing_pii_key() -> None:
    text = "some text"
    assert apply_redactions(text, {}) == text
