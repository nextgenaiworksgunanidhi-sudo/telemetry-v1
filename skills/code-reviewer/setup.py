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
import urllib.request
from pathlib import Path

_SETUP_DIR = Path(__file__).parent.resolve()
_SKILL_ITEMS = ["scripts", "telemetry.yaml", "config.yaml", "SKILL.md"]
_VENV_PYTHON = Path.home() / ".jpmc-skills" / ".venv" / "bin" / "python3"


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


def _python_path() -> str:
    """Return absolute path to the venv python, falling back to sys.executable."""
    return str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable


def _hook_commands(skill_dst: Path) -> tuple[str, str]:
    """Build absolute hook command strings for pre- and post-invoke scripts."""
    python = _python_path()
    pre  = skill_dst / "scripts" / "hooks" / "pre-invoke.py"
    post = skill_dst / "scripts" / "hooks" / "post-invoke.py"
    return f"{python} {pre}", f"{python} {post}"


def _merge_hooks(settings: dict, pre_cmd: str, post_cmd: str) -> dict:
    """Add pre/post hook entries without removing unrelated existing hooks."""
    hooks = settings.setdefault("hooks", {})
    pre_entry  = {"matcher": "", "hooks": [{"type": "command", "command": pre_cmd,  "timeout": 10}]}
    post_entry = {"matcher": "", "hooks": [{"type": "command", "command": post_cmd, "timeout": 15}]}
    user_hooks = hooks.setdefault("UserPromptSubmit", [])
    user_hooks[:] = [h for h in user_hooks if "code-reviewer" not in str(h)]
    user_hooks.append(pre_entry)
    stop_hooks = hooks.setdefault("Stop", [])
    stop_hooks[:] = [h for h in stop_hooks if "code-reviewer" not in str(h)]
    stop_hooks.append(post_entry)
    return settings


def _check_jaeger() -> None:
    """Warn if Jaeger is not reachable on localhost:16686. Never blocks install."""
    try:
        r = urllib.request.urlopen("http://localhost:16686/api/services", timeout=3)
        services = json.loads(r.read())
        if services.get("errors") is None:
            print("  [check] Jaeger verified on localhost:16686")
        else:
            print("  [warn]  Port 4318 may have a conflict")
    except Exception:
        print("  [warn]  Jaeger not detected on localhost:16686")
        print("          Make sure Jaeger is running before using")
        print("          the skill or traces will be buffered")


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
    pre_cmd, post_cmd = _hook_commands(skill_dst)
    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  JPMC AI Platform — code-reviewer skill setup")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print(f"  Python   : {_python_path()}")
    print(f"  Pre-hook : {pre_cmd}")
    print(f"  Post-hook: {post_cmd}")
    print()
    _copy_skill(skill_dst)
    _check_jaeger()
    settings = _load_settings(settings_path)
    settings = _merge_hooks(settings, pre_cmd, post_cmd)
    _write_settings(settings_path, settings)
    _install_deps(requirements)
    _print_summary(skill_dst, settings_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[setup] ERROR: {exc}")
    sys.exit(0)
