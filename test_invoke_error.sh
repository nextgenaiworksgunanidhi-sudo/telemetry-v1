#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"

echo "--- Simulating skill invocation (ERROR) ---"
cd "$SCRIPT_DIR/skills/code-reviewer"

echo '{"prompt": "/code-reviewer Analyse authentication logic in this Java class"}' \
  | "$VENV_PYTHON" scripts/hooks/pre-invoke.py

echo "--- Skill executing (sleeping 1s) ---"
sleep 1

echo '{"last_assistant_message": ""}' \
  | "$VENV_PYTHON" scripts/hooks/post-invoke.py

echo "--- Done. Open http://localhost:16686 to verify error trace ---"
