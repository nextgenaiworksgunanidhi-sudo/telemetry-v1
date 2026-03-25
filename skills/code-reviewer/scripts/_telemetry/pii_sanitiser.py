"""
pii_sanitiser.py — Redacts PII from prompt and response text before export.
Never raises. Returns safe defaults on any error or missing input.
"""

import hashlib
import re
from typing import Optional


def apply_redactions(text: str, config: dict) -> str:
    """
    Apply every regex redaction pattern from config['pii']['redact_patterns']
    to text and return the redacted result.
    """
    try:
        patterns = config.get("pii", {}).get("redact_patterns", [])
        for entry in patterns:
            pattern = entry.get("pattern", "")
            replacement = entry.get("replacement", "[REDACTED]")
            if pattern:
                text = re.sub(pattern, replacement, text)
        return text
    except Exception:
        return text


def sanitise(
    raw_prompt: Optional[str],
    raw_response: Optional[str],
    config: dict,
) -> dict:
    """
    Sanitise prompt and response for safe export in OTel span attributes.

    Returns:
        prompt_hash         — sha256 of full raw prompt (before any changes)
        prompt_preview      — redacted + truncated prompt
        prompt_char_count   — length of original raw prompt
        response_preview    — redacted + truncated response
        response_char_count — length of original raw response
        response_truncated  — True if response was longer than max_chars
    """
    try:
        pii_cfg = config.get("pii", {})
        prompt_max = int(pii_cfg.get("prompt_max_chars", 500))
        response_max = int(pii_cfg.get("response_max_chars", 300))

        # Normalise inputs — treat None/missing as empty string
        raw_prompt = raw_prompt if raw_prompt else ""
        raw_response = raw_response if raw_response else ""

        # Hash computed on FULL raw prompt BEFORE any truncation or redaction
        prompt_hash = hashlib.sha256(raw_prompt.encode()).hexdigest()

        prompt_preview = apply_redactions(raw_prompt, config)[:prompt_max]
        prompt_char_count = len(raw_prompt)

        response_redacted = apply_redactions(raw_response, config)
        response_preview = response_redacted[:response_max]
        response_char_count = len(raw_response)
        response_truncated = len(raw_response) > response_max

        return {
            "prompt_hash": prompt_hash,
            "prompt_preview": prompt_preview,
            "prompt_char_count": prompt_char_count,
            "response_preview": response_preview,
            "response_char_count": response_char_count,
            "response_truncated": response_truncated,
        }

    except Exception:
        return {
            "prompt_hash": hashlib.sha256(b"").hexdigest(),
            "prompt_preview": "",
            "prompt_char_count": 0,
            "response_preview": "",
            "response_char_count": 0,
            "response_truncated": False,
        }


if __name__ == "__main__":
    import json

    CONFIG = {
        "pii": {
            "prompt_max_chars": 500,
            "response_max_chars": 300,
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

    # Test case 1: Normal prompt with embedded email
    print("=== Test 1: Email redaction ===")
    result = sanitise(
        raw_prompt="Review code for user john.smith@jpmc.com please.",
        raw_response="Code looks fine.",
        config=CONFIG,
    )
    print(json.dumps(result, indent=2))
    assert "[REDACTED-EMAIL]" in result["prompt_preview"], "Email not redacted!"
    assert len(result["prompt_hash"]) == 64, "Hash must be 64 chars!"
    print("PASS\n")

    # Test case 2: Prompt containing a fake JWT token
    print("=== Test 2: JWT redaction ===")
    result = sanitise(
        raw_prompt="Token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMTIzIn0.abc123def456",
        raw_response="JWT detected.",
        config=CONFIG,
    )
    print(json.dumps(result, indent=2))
    assert "[REDACTED-JWT]" in result["prompt_preview"], "JWT not redacted!"
    assert len(result["prompt_hash"]) == 64, "Hash must be 64 chars!"
    print("PASS\n")

    # Test case 3: Empty prompt
    print("=== Test 3: Empty prompt ===")
    result = sanitise(
        raw_prompt="",
        raw_response="",
        config=CONFIG,
    )
    print(json.dumps(result, indent=2))
    assert result["prompt_preview"] == "", "Empty prompt preview should be empty!"
    assert result["prompt_char_count"] == 0, "Empty prompt count should be 0!"
    assert len(result["prompt_hash"]) == 64, "Hash must be 64 chars even for empty!"
    print("PASS\n")

    print("All tests passed.")
