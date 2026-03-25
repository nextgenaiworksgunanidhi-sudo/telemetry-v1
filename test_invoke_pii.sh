#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"

echo "--- Simulating invocation with PII in prompt ---"
cd "$SCRIPT_DIR/skills/code-reviewer"

echo '{"prompt": "/code-reviewer Review code for user john.smith@jpmc.com account 123456789, JWT is eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMTIzIn0.abc123def SSN 123-45-6789 and SID9876543 records."}' \
  | "$VENV_PYTHON" scripts/hooks/pre-invoke.py

sleep 1

echo '{"last_assistant_message": "Reviewed the code. Handles sensitive customer data. Recommend encrypting all fields at rest and using vault for secrets."}' \
  | "$VENV_PYTHON" scripts/hooks/post-invoke.py

echo "--- Done. Verify PII is redacted in Jaeger span attributes ---"
