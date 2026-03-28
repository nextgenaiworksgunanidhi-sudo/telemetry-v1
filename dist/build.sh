#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# xyz AI Platform — skill package builder
#
# Produces a distributable zip:
#   dist/code-reviewer-<version>.zip
#
# Archive extracts to:
#   code-reviewer-<version>/
#   ├── setup.py            ← developer runs this once from their project root
#   ├── requirements.txt
#   ├── SKILL.md
#   ├── config.yaml
#   ├── telemetry.yaml
#   └── scripts/
#       ├── hooks/
#       │   ├── pre-invoke.py
#       │   └── post-invoke.py
#       └── _telemetry/
#           ├── __init__.py, sdk.py, env_capture.py, exporter.py, pii_sanitiser.py
#
# Usage (from project root):
#   ./dist/build.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL_SRC="$PROJECT_ROOT/skills/code-reviewer"
REQUIREMENTS="$PROJECT_ROOT/requirements.txt"

# ── Read version from telemetry.yaml ─────────────────────────────────────────
VERSION=$(grep 'skill_version:' "$SKILL_SRC/telemetry.yaml" | awk '{print $2}' | tr -d '"')
TOP_DIR="code-reviewer-${VERSION}"
ARCHIVE_NAME="${TOP_DIR}.zip"
ARCHIVE_PATH="$SCRIPT_DIR/$ARCHIVE_NAME"

echo "Building $ARCHIVE_NAME ..."

# ── Stage files under versioned top-level directory ───────────────────────────
STAGING=$(mktemp -d)
trap 'rm -rf "$STAGING"' EXIT

STAGE="$STAGING/$TOP_DIR"
mkdir -p "$STAGE/scripts/hooks"
mkdir -p "$STAGE/scripts/_telemetry"

# setup.py and requirements.txt go at the archive root
cp "$SKILL_SRC/setup.py"  "$STAGE/setup.py"
cp "$REQUIREMENTS"         "$STAGE/requirements.txt"

# Skill metadata
for f in SKILL.md config.yaml telemetry.yaml; do
    cp "$SKILL_SRC/$f" "$STAGE/$f"
done

# scripts/hooks — only the two active hooks
cp "$SKILL_SRC/scripts/hooks/pre-invoke.py"  "$STAGE/scripts/hooks/pre-invoke.py"
cp "$SKILL_SRC/scripts/hooks/post-invoke.py" "$STAGE/scripts/hooks/post-invoke.py"

# scripts/_telemetry package — exclude __pycache__
rsync -a \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    "$SKILL_SRC/scripts/_telemetry/" "$STAGE/scripts/_telemetry/"

# ── Create zip ────────────────────────────────────────────────────────────────
rm -f "$ARCHIVE_PATH"
(cd "$STAGING" && zip -r "$ARCHIVE_PATH" "$TOP_DIR" \
    -x '*/__pycache__/*' -x '*.pyc' -x '*.pyo' > /dev/null)

# ── Report ────────────────────────────────────────────────────────────────────
BYTES=$(wc -c < "$ARCHIVE_PATH" | tr -d ' ')
echo ""
echo "Archive  : $ARCHIVE_PATH"
echo "Size     : $BYTES bytes"
echo ""
echo "Contents:"
unzip -l "$ARCHIVE_PATH" | grep -E '^\s+[0-9]' | awk '{print $NF}' | grep -v '^files$' | sort | sed 's/^/  /'
echo ""
echo "Done. Distribute $ARCHIVE_NAME to developers."
echo ""
echo "Developer setup:"
echo "  unzip $ARCHIVE_NAME"
echo "  cd /your/project/root"
echo "  python3 /path/to/$TOP_DIR/setup.py"
