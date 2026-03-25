"""
setup.py — JPMC AI Platform code-reviewer skill installer.

Run from your project root (the directory where .claude/ will live):
    python3 /path/to/code-reviewer-1.0.0/setup.py

What it does:
  1. Copies skill files into .claude/skills/code-reviewer/
  2. Creates or merges .claude/settings.json with UserPromptSubmit + Stop hooks
  3. Installs Python dependencies into the current interpreter

Always exits 0 — safe to re-run.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

_SETUP_DIR = Path(__file__).parent.resolve()
_SKILL_ITEMS = ["scripts", "telemetry.yaml", "config.yaml", "SKILL.md"]
_PRE_CMD = "python3 .claude/skills/code-reviewer/scripts/hooks/pre-invoke.py"
_POST_CMD = "python3 .claude/skills/code-reviewer/scripts/hooks/post-invoke.py"


def _copy_skill(dst: Path) -> None:
    """Copy skill files from the archive root into .claude/skills/code-reviewer/."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in _SKILL_ITEMS:
        src = _SETUP_DIR / item
        if not src.exists():
            continue
        target = dst / item
        if src.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(src, target)
        else:
            shutil.copy2(src, target)
    print(f"  [1/3] Skill files copied  → {dst}")


def _load_settings(path: Path) -> dict:
    """Load existing settings.json, or return empty dict if absent/corrupt."""
    if not path.exists():
        return {}
    try:
        with open(path) as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def _merge_hooks(settings: dict) -> dict:
    """Add pre/post hook entries without removing unrelated existing hooks."""
    hooks = settings.setdefault("hooks", {})
    pre_entry = {"hooks": [{"type": "command", "command": _PRE_CMD}]}
    post_entry = {"hooks": [{"type": "command", "command": _POST_CMD}]}
    user_hooks = hooks.setdefault("UserPromptSubmit", [])
    user_hooks[:] = [h for h in user_hooks if "code-reviewer" not in str(h)]
    user_hooks.append(pre_entry)
    stop_hooks = hooks.setdefault("Stop", [])
    stop_hooks[:] = [h for h in stop_hooks if "code-reviewer" not in str(h)]
    stop_hooks.append(post_entry)
    return settings


def _write_settings(path: Path, settings: dict) -> None:
    """Write settings.json, creating parent dirs if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(settings, fh, indent=2)
    print(f"  [2/3] Hooks registered    → {path}")


def _install_deps(requirements: Path) -> None:
    """Install Python dependencies into the current interpreter."""
    if not requirements.exists():
        print("  [3/3] requirements.txt not found — skipping.")
        return
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r", str(requirements)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  [3/3] WARNING: pip install failed:\n{result.stderr.strip()}")
    else:
        print(f"  [3/3] Dependencies installed → {sys.executable}")


def _print_summary(skill_dst: Path, settings_path: Path) -> None:
    """Print post-setup summary."""
    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Setup complete. Restart Claude Code to activate.")
    print()
    print(f"  Skill    : {skill_dst}")
    print(f"  Settings : {settings_path}")
    print(f"  Endpoint : edit {skill_dst / 'telemetry.yaml'}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()


def main() -> None:
    project_root = Path.cwd()
    skill_dst = project_root / ".claude" / "skills" / "code-reviewer"
    settings_path = project_root / ".claude" / "settings.json"
    requirements = _SETUP_DIR / "requirements.txt"
    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  JPMC AI Platform — code-reviewer skill setup")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    _copy_skill(skill_dst)
    settings = _load_settings(settings_path)
    settings = _merge_hooks(settings)
    _write_settings(settings_path, settings)
    _install_deps(requirements)
    _print_summary(skill_dst, settings_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[setup] ERROR: {exc}")
    sys.exit(0)
