"""
fallback_buffer.py — Local trace buffer for when Jaeger is unreachable.

Provides two public functions:
  buffer_span(span_data, config)  — append a failed trace to the JSONL buffer
  flush_pending(config)           — retry all buffered traces via OTLP HTTP
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def buffer_span(span_data: dict, config: dict) -> None:
    """
    Append a failed trace to the local JSONL buffer file.

    span_data must contain: span_name, trace_id, span_id, attributes.
    Does nothing if fallback.enabled is False. Never raises.
    """
    try:
        fallback = config.get("fallback", {})
        if not fallback.get("enabled", False):
            return

        buffer_path = Path(os.path.expanduser(fallback["buffer_path"]))
        buffer_path.parent.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "attempt": 1,
            "first_failed_at": now,
            "last_attempted_at": now,
            "span_name": span_data["span_name"],
            "trace_id": span_data["trace_id"],
            "span_id": span_data.get("span_id", ""),
            "attributes": span_data.get("attributes", {}),
        }

        with open(buffer_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

        sys.stderr.write(
            f"[fallback_buffer] Buffered span '{entry['span_name']}' "
            f"trace_id={entry['trace_id']}\n"
        )
    except Exception as exc:
        sys.stderr.write(f"[fallback_buffer] ERROR in buffer_span: {exc}\n")


def flush_pending(config: dict) -> dict:
    """
    Retry all pending buffered traces via direct OTLP HTTP POST.

    Returns {"flushed": N, "failed": N, "dropped": N}.
    Never raises.
    """
    summary = {"flushed": 0, "failed": 0, "dropped": 0}
    try:
        fallback = config.get("fallback", {})
        if not fallback.get("enabled", False):
            return summary

        buffer_path = Path(os.path.expanduser(fallback["buffer_path"]))
        if not buffer_path.exists():
            return summary

        max_retries = int(fallback.get("max_retries", 5))
        error_log_path = Path(
            os.path.expanduser(config.get("error_log_path", "~/.jpmc-skills/telemetry.err"))
        )
        endpoint = config.get("endpoint", "http://localhost:4318").rstrip("/")

        with open(buffer_path, "r", encoding="utf-8") as fh:
            raw_lines = fh.readlines()

        remaining: list[str] = []

        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                sys.stderr.write("[fallback_buffer] Skipping malformed JSONL line\n")
                continue

            if _export_entry(entry, endpoint):
                summary["flushed"] += 1
            else:
                entry["attempt"] = entry.get("attempt", 1) + 1
                entry["last_attempted_at"] = datetime.now(timezone.utc).isoformat()

                if entry["attempt"] > max_retries:
                    summary["dropped"] += 1
                    _log_dropped(error_log_path, entry)
                else:
                    summary["failed"] += 1
                    remaining.append(json.dumps(entry))

        if remaining:
            with open(buffer_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(remaining) + "\n")
        else:
            try:
                buffer_path.unlink()
            except FileNotFoundError:
                pass

    except Exception as exc:
        sys.stderr.write(f"[fallback_buffer] ERROR in flush_pending: {exc}\n")

    return summary


def _export_entry(entry: dict, endpoint: str) -> bool:
    """Send one buffered span to the OTLP endpoint. Returns True on success."""
    try:
        payload = {
            "resourceSpans": [{
                "scopeSpans": [{
                    "spans": [{
                        "traceId": entry["trace_id"],
                        "spanId": entry.get("span_id", ""),
                        "name": entry["span_name"],
                        "attributes": [
                            {"key": k, "value": {"stringValue": str(v)}}
                            for k, v in entry.get("attributes", {}).items()
                        ],
                    }]
                }]
            }]
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{endpoint}/v1/traces",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


def _log_dropped(error_log_path: Path, entry: dict) -> None:
    """Write a DROPPED line to the error log."""
    try:
        error_log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        n = entry.get("attempt", 0)
        trace_id = entry.get("trace_id", "unknown")
        with open(error_log_path, "a", encoding="utf-8") as fh:
            fh.write(f"[{timestamp}] DROPPED: trace {trace_id} after {n} attempts\n")
    except Exception as exc:
        sys.stderr.write(f"[fallback_buffer] ERROR writing drop log: {exc}\n")


if __name__ == "__main__":
    import tempfile

    print("=== fallback_buffer standalone test ===\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        test_config = {
            "endpoint": "http://localhost:4318",
            "error_log_path": f"{tmpdir}/telemetry.err",
            "fallback": {
                "enabled": True,
                "buffer_path": f"{tmpdir}/pending_traces.jsonl",
                "max_retries": 5,
            },
        }

        test_span = {
            "span_name": "skill.completion",
            "trace_id": "abc123def456abc123def456abc12301",
            "span_id": "abc123def456abc1",
            "attributes": {"skill.name": "code-reviewer", "skill.outcome": "success"},
        }

        print("1. Writing test span to buffer...")
        buffer_span(test_span, test_config)

        buf = Path(test_config["fallback"]["buffer_path"])
        if buf.exists():
            contents = buf.read_text(encoding="utf-8").strip()
            print(f"2. Buffer contents:\n{contents}\n")
        else:
            print("2. Buffer file not found!\n")

        print("3. Flushing pending traces (Jaeger likely not running — expect failed=1)...")
        result = flush_pending(test_config)
        print(f"4. Flush summary: {result}\n")

    print("=== done ===")
