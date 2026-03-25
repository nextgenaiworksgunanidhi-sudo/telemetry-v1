"""
pre-invoke.py — Claude Code UserPromptSubmit hook.

Fires on every UserPromptSubmit event. Caches the raw prompt, opens the
OTel root span, and writes span context to /tmp for post-invoke.py to
continue. Telemetry captures all interactions, not only slash commands.

Always exits 0 — never blocks the agent.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

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
    """Start OTel root span, write context to /tmp, then end and flush it."""
    from _telemetry import env_capture, sdk
    resource_attrs = env_capture.get_resource_attributes()
    extra_attrs = {
        "_resource_attrs": resource_attrs,
        "invoke.timestamp": datetime.now(timezone.utc).isoformat(),
        "skill.id": config.get("skill_id", "unknown"),
        "skill.name": config.get("skill_name", "unknown"),
        "skill.version": config.get("skill_version", "0.0.0"),
    }
    tracer_provider, span = sdk.start_skill_span(config, extra_attrs)
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

    # End and flush the root span so it reaches Jaeger.
    # trace_id and span_id are already saved above for post-invoke to
    # reference as the parent of the skill.completion child span.
    span.end()
    tracer_provider.force_flush(timeout_millis=3000)
    tracer_provider.shutdown()


def main() -> None:
    prompt = _read_prompt()
    if not prompt.strip():
        return
    _cache_prompt(prompt)
    import yaml
    with open(_TELEMETRY_YAML, "r") as fh:
        config = yaml.safe_load(fh)

    # Attempt to flush any pending buffered traces before opening a new span
    try:
        from _telemetry import fallback_buffer
        flush_result = fallback_buffer.flush_pending(config)
        if flush_result["flushed"] > 0:
            sys.stderr.write(
                f"[telemetry] Flushed {flush_result['flushed']} "
                f"pending trace(s) from buffer\n"
            )
        if flush_result["dropped"] > 0:
            sys.stderr.write(
                f"[telemetry] Dropped {flush_result['dropped']} "
                f"trace(s) after max retries\n"
            )
    except Exception as exc:
        sys.stderr.write(f"[pre-invoke] WARNING: flush_pending failed: {exc}\n")

    _open_span(config)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write(f"[pre-invoke] WARNING: {exc}\n")
    sys.exit(0)
