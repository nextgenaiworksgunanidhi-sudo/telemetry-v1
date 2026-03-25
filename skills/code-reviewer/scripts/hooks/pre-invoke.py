"""
pre-invoke.py — Claude Code UserPromptSubmit hook.

Reads the UserPromptSubmit stdin event, detects skill invocations
(/code-reviewer prefix), caches the raw prompt, opens the OTel root span,
and writes span context to /tmp for post-invoke.py to continue.

Always exits 0 — never blocks the agent.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SKILL_PREFIX = "/code-reviewer"
_PROMPT_CACHE = Path("/tmp/jpmc_skill_user_prompt.txt")
_SPAN_CTX_FILE = Path("/tmp/jpmc_skill_span_ctx.json")
_SKILL_ROOT = Path(__file__).parent.parent.resolve()          # scripts/
_TELEMETRY_YAML = _SKILL_ROOT.parent / "telemetry.yaml"      # code-reviewer/telemetry.yaml

sys.path.insert(0, str(_SKILL_ROOT))                          # adds scripts/ for _telemetry imports


def _read_prompt() -> str:
    """Parse prompt from Claude Code UserPromptSubmit stdin JSON."""
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        return ""
    return data.get("prompt", "")


def _cache_prompt(prompt: str) -> None:
    """Write raw prompt to temp file for post-invoke.py to retrieve."""
    try:
        _PROMPT_CACHE.write_text(prompt, encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"[pre-invoke] WARNING: could not write prompt cache: {exc}\n")


def _open_span(config: dict) -> None:
    """Start OTel root span and write context to /tmp for post-invoke.py."""
    from _telemetry import env_capture, sdk
    resource_attrs = env_capture.get_resource_attributes()
    extra_attrs = {
        "_resource_attrs": resource_attrs,
        "invoke.timestamp": datetime.now(timezone.utc).isoformat(),
        "skill.id": config.get("skill_id", "unknown"),
        "skill.name": config.get("skill_name", "unknown"),
        "skill.version": config.get("skill_version", "0.0.0"),
    }
    _, span = sdk.start_skill_span(config, extra_attrs)
    span_ctx = span.get_span_context()
    ctx_data = {
        "trace_id": format(span_ctx.trace_id, "032x"),
        "span_id": format(span_ctx.span_id, "016x"),
        "start_time_iso": datetime.now(timezone.utc).isoformat(),
        "telemetry_yaml_path": str(_TELEMETRY_YAML),
    }
    with open(_SPAN_CTX_FILE, "w") as fh:
        json.dump(ctx_data, fh, indent=2)
    sys.stderr.write(f"[pre-invoke] trace_id={ctx_data['trace_id']}\n")


def main() -> None:
    prompt = _read_prompt()
    if not prompt.strip().startswith(_SKILL_PREFIX):
        return
    _cache_prompt(prompt)
    import yaml
    with open(_TELEMETRY_YAML, "r") as fh:
        config = yaml.safe_load(fh)
    _open_span(config)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write(f"[pre-invoke] WARNING: {exc}\n")
    sys.exit(0)
