#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"

echo "--- Simulating skill invocation (SUCCESS) ---"
cd "$SCRIPT_DIR/skills/code-reviewer"

echo '{"prompt": "/code-reviewer Review this Python function for security issues: def get_user(user_id): query = SELECT * FROM users WHERE id= + user_id"}' \
  | "$VENV_PYTHON" scripts/hooks/pre-invoke.py

echo "--- Skill executing (sleeping 2s) ---"
sleep 2

echo '{"last_assistant_message": "I found a critical SQL injection vulnerability. Use parameterised queries: db.execute(SELECT * FROM users WHERE id=?, (user_id,)). This is a high severity finding per JPMC coding standards."}' \
  | "$VENV_PYTHON" scripts/hooks/post-invoke.py

echo "--- Done. Open http://localhost:16686 to verify traces ---"
