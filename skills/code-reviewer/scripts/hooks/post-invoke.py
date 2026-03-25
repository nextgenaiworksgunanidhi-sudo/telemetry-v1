"""
post-invoke.py — Claude Code Stop hook.

Reads the Stop event from stdin, retrieves the cached prompt written by
pre-invoke.py, reconstructs the parent OTel span, attaches PII-sanitised
prompt/response attributes, flushes to Jaeger, and cleans up.

Always exits 0 — never blocks the agent.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SPAN_CTX_FILE = Path("/tmp/jpmc_skill_span_ctx.json")
_PROMPT_CACHE = Path("/tmp/jpmc_skill_user_prompt.txt")
_SKILL_ROOT = Path(__file__).parent.parent.resolve()

sys.path.insert(0, str(_SKILL_ROOT))


def _read_stop_event() -> str:
    """Parse LLM response from Claude Code Stop hook stdin JSON."""
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        return ""
    return data.get("last_assistant_message", "")


def _read_prompt_cache() -> str:
    """Read cached prompt from pre-invoke.py and delete the temp file."""
    prompt = ""
    try:
        if _PROMPT_CACHE.exists():
            prompt = _PROMPT_CACHE.read_text(encoding="utf-8")
    except OSError:
        pass
    finally:
        _PROMPT_CACHE.unlink(missing_ok=True)
    return prompt


def _load_span_ctx() -> "dict | None":
    """Load span context written by pre-invoke.py; None if absent."""
    if not _SPAN_CTX_FILE.exists():
        return None
    with open(_SPAN_CTX_FILE, "r") as fh:
        return json.load(fh)


def _calc_duration_ms(start_time_iso: str) -> float:
    """Return elapsed milliseconds from an ISO timestamp string to now."""
    try:
        start = datetime.fromisoformat(start_time_iso)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - start).total_seconds() * 1000.0
    except Exception:
        return 0.0


def _build_parent_ctx(ctx_data: dict):
    """Reconstruct OTel parent context from stored trace/span IDs."""
    from opentelemetry import trace
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
    parent_sc = SpanContext(
        trace_id=int(ctx_data["trace_id"], 16),
        span_id=int(ctx_data["span_id"], 16),
        is_remote=True,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    return trace.set_span_in_context(NonRecordingSpan(parent_sc))


def _build_provider(config: dict) -> tuple:
    """Create TracerProvider and tracer for the child span."""
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from _telemetry import env_capture
    skill_id = config.get("skill_id", "unknown")
    attrs = env_capture.get_resource_attributes()
    attrs.update({"skill.id": skill_id, "service.name": skill_id,
                  "skill.version": config.get("skill_version", "0.0.0")})
    endpoint = config.get("endpoint", "http://localhost:4318")
    exp = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
    proc = BatchSpanProcessor(exp,
                              max_export_batch_size=int(config.get("batch_size", 20)),
                              schedule_delay_millis=int(config.get("flush_interval_ms", 3000)))
    provider = TracerProvider(resource=Resource.create(attrs))
    provider.add_span_processor(proc)
    return provider, provider.get_tracer(skill_id)


def _set_span_status(span, outcome: str, error_msg: str) -> None:
    """Set span status and record exception if outcome is error."""
    from opentelemetry.trace import StatusCode
    if outcome == "error":
        if error_msg:
            span.set_attribute("error.message", error_msg)
            span.record_exception(Exception(error_msg))
        span.set_status(StatusCode.ERROR, error_msg or "skill exited non-zero")
    else:
        span.set_status(StatusCode.OK)


def _record_span(tracer, parent_ctx, config: dict, ctx_data: dict,
                 outcome: str, error_msg: str, pii_result: dict,
                 duration_ms: float) -> None:
    """Open child span, attach all attributes, and close it."""
    with tracer.start_as_current_span("skill.completion", context=parent_ctx) as span:
        span.set_attribute("skill.id", config.get("skill_id", "unknown"))
        span.set_attribute("skill.name", config.get("skill_name", "unknown"))
        span.set_attribute("skill.version", config.get("skill_version", "0.0.0"))
        span.set_attribute("invoke.timestamp", ctx_data.get("start_time_iso", ""))
        span.set_attribute("invoke.duration_ms", round(duration_ms, 2))
        span.set_attribute("skill.outcome", outcome)
        span.set_attribute("prompt.hash", pii_result["prompt_hash"])
        span.set_attribute("prompt.preview", pii_result["prompt_preview"])
        span.set_attribute("prompt.char_count", pii_result["prompt_char_count"])
        span.set_attribute("response.preview", pii_result["response_preview"])
        span.set_attribute("response.char_count", pii_result["response_char_count"])
        span.set_attribute("response.truncated", pii_result["response_truncated"])
        _set_span_status(span, outcome, error_msg)


def main() -> None:
    llm_response = _read_stop_event()
    raw_prompt = _read_prompt_cache()
    ctx_data = _load_span_ctx()
    if ctx_data is None:
        return
    import yaml
    from _telemetry import exporter, pii_sanitiser
    with open(Path(ctx_data["telemetry_yaml_path"]), "r") as fh:
        config = yaml.safe_load(fh)
    pii_result = pii_sanitiser.sanitise(raw_prompt, llm_response, config)
    duration_ms = _calc_duration_ms(ctx_data.get("start_time_iso", ""))
    parent_ctx = _build_parent_ctx(ctx_data)
    provider, tracer = _build_provider(config)
    _record_span(tracer, parent_ctx, config, ctx_data, "success", "", pii_result, duration_ms)
    exporter.safe_flush(provider, config.get("error_log_path", "~/.jpmc-skills/telemetry.err"))
    provider.force_flush(timeout_millis=5000)
    provider.shutdown()
    _SPAN_CTX_FILE.unlink(missing_ok=True)
    sys.stderr.write(f"[post-invoke] outcome=success duration_ms={round(duration_ms,2)}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write(f"[post-invoke] WARNING: {exc}\n")
    sys.exit(0)
