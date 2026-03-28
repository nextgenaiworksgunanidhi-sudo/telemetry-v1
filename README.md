# xyz AI Platform — Telemetry System

End-to-end observability for xyz AI skills. When a developer invokes a skill,
Python hook scripts fire automatically, capture the user prompt and LLM response,
apply PII redaction, and export OpenTelemetry traces to Jaeger — all with zero
developer configuration.

---

## What This Is

- **Pre-invoke hook** opens an OTel root span before the skill runs, capturing environment metadata.
- **Post-invoke hook** reopens that span as a parent, sanitises prompt/response through the PII module, attaches all attributes, and flushes to Jaeger.
- **PII sanitiser** truncates and regex-redacts email, SID, account numbers, JWT tokens, and SSNs before any data leaves the machine.
- **Silent failure** — all network errors are swallowed; hooks always exit 0 and never block the agent.

---

## Prerequisites

- Python 3.10+
- Docker with Jaeger running:

```bash
docker run -d --name jaeger \
  -p 4318:4318 \
  -p 16686:16686 \
  jaegertracing/all-in-one:latest
```

---

## How to Use This Skill (Developer Instructions)

1. Download `code-reviewer-1.0.0.zip` from the xyz AI marketplace
2. Unzip it anywhere on your machine
3. From your **project root**, run:
   ```bash
   python3 /path/to/code-reviewer-1.0.0/setup.py
   ```
4. Restart Claude Code
5. Start using Claude Code normally — telemetry is automatic

That is all. No pip install, no config, no environment variables.

---

## Simulate Traces (Platform Team / Dev Repo Only)

These scripts simulate hook invocations from the source repo:

**Success trace:**
```bash
./test_invoke.sh
```

**Error trace:**
```bash
./test_invoke_error.sh
```

**PII redaction trace:**
```bash
./test_invoke_pii.sh
```

---

## Verify Traces in Jaeger

Open the Jaeger UI: **http://localhost:16686**

1. Select service **`jpmc.ai-skills.code-reviewer`** from the dropdown.
2. Click **Find Traces**.
3. Click on any trace to expand it and inspect span attributes.

Key attributes to look for:

| Attribute | Description |
|-----------|-------------|
| `prompt.hash` | 64-char sha256 of full raw prompt (for correlation) |
| `prompt.preview` | Truncated + redacted prompt text |
| `prompt.char_count` | Character count of the original prompt |
| `response.preview` | Truncated + redacted LLM response |
| `skill.outcome` | `success` or `error` |
| `invoke.duration_ms` | Total skill execution time in milliseconds |
| `error.message` | Present only when `skill.outcome=error` |

---

## Verify PII Redaction

Run `./test_invoke_pii.sh`, then in Jaeger inspect `prompt.preview`. You should see:

```
Review code for user [REDACTED-EMAIL] account [REDACTED-ACCT],
JWT is [REDACTED-JWT]
SSN [REDACTED-SSN] and [REDACTED-SID] records.
```

`prompt.hash` will still be a 64-character hex string — computed from the full raw
prompt before any redaction, allowing trace correlation without storing raw content.

---

## Add Custom Redaction Patterns

Edit `.claude/skills/code-reviewer/telemetry.yaml` (installed path) under `pii.redact_patterns`:

```yaml
pii:
  redact_patterns:
    - name: "my_pattern"
      pattern: '\bMY-REGEX-HERE\b'
      replacement: "[REDACTED-CUSTOM]"
```

Patterns are applied in order using `re.sub`. Changes take effect immediately
on the next hook invocation — no restart required.

---

## Switch to Production Endpoint

Edit `.claude/skills/code-reviewer/telemetry.yaml` (installed path):

```yaml
endpoint: "https://your-prod-otlp-collector.internal/v1/traces"
```

The hook scripts read this file at runtime on every invocation.

---

## Silent Failure Behaviour

If the OTLP endpoint is unreachable, hooks still exit 0 and the agent is
never blocked. Export errors are logged with timestamps to:

```
~/.jpmc-skills/telemetry.err
```

Example entry:
```
[2026-03-24 16:35:18] FLUSH_ERROR: force_flush returned False (timeout or export failure)
```

---

## Test Suite

All tests live in `skills/code-reviewer/tests/`. Run from the project root:

```bash
cd skills/code-reviewer
python -m pytest tests/ -v
```

| Test file | What it covers |
|-----------|----------------|
| `test_cc_pre_invoke.py` | `pre-invoke.py` — skill detection, stdin parsing, prompt caching, silent handling of bad JSON / missing keys |
| `test_cc_post_invoke.py` | `post-invoke.py` — span-ctx gate, stdin reading, prompt cache cleanup, silent failure handling |
| `test_pii_sanitiser.py` | Regex redaction for email, SID, account numbers, JWT tokens, SSNs; truncation; hash stability |
| `test_sdk.py` | TracerProvider setup, span start/end helpers, context file read/write |
| `test_env_capture.py` | Resource attribute collection (host, IDE, runtime metadata) |
| `test_exporter.py` | Safe flush wrapper — error log fallback when endpoint is unreachable |

Every module covers the happy path and at least one failure/edge case.

---

## Build & Distribute

### Build the archive

```bash
./dist/build.sh
```

Produces `dist/code-reviewer-<version>.zip`. Version is read from `skills/code-reviewer/telemetry.yaml`.

### What the zip contains

```
code-reviewer-1.0.0/
├── setup.py            ← developer runs this once from their project root
├── requirements.txt
├── skill.md
├── config.yaml
├── telemetry.yaml
├── hooks/
│   ├── pre-invoke.py
│   └── post-invoke.py
└── _telemetry/
    ├── __init__.py
    ├── sdk.py
    ├── env_capture.py
    ├── exporter.py
    └── pii_sanitiser.py
```

### What `setup.py` does on the developer's machine

1. Copies skill files into `<project-root>/.claude/skills/code-reviewer/`
2. Creates or merges `<project-root>/.claude/settings.json` with `UserPromptSubmit` + `Stop` hook entries (non-destructive — existing entries are preserved)
3. Installs Python dependencies into the current interpreter

Hooks use relative paths (`python3 .claude/skills/...`) so the project is portable across teammates — anyone who clones the repo gets working hooks without re-running setup.

---

## Folder Structure

```
telemetry-v1/
├── README.md                      # This file
├── requirements.txt               # Python dependencies (OTel SDK + PyYAML)
├── .gitignore                     # Ignores __pycache__, .venv, *.err, etc.
├── test_invoke.sh                 # Simulate a successful skill invocation
├── test_invoke_error.sh           # Simulate a failed skill invocation
├── test_invoke_pii.sh             # Simulate invocation with PII in prompt
├── dist/
│   ├── build.sh                   # Produces dist/code-reviewer-<version>.zip
│   └── code-reviewer-1.0.0.zip    # Distributable archive (output of build.sh)
└── skills/
    └── code-reviewer/
        ├── setup.py               # Developer runs this once to install the skill
        ├── skill.md               # xyz code review prompt template
        ├── config.yaml            # Skill metadata
        ├── telemetry.yaml         # OTel endpoint, PII rules, batch settings
        ├── hooks/
        │   ├── pre-invoke.py      # UserPromptSubmit hook — detects skill, opens span
        │   └── post-invoke.py     # Stop hook — closes span, sanitises PII, flushes
        ├── _telemetry/
        │   ├── __init__.py        # Package marker (empty)
        │   ├── sdk.py             # TracerProvider setup, span start/end helpers
        │   ├── env_capture.py     # Collects host/IDE/runtime resource attributes
        │   ├── exporter.py        # Safe flush wrapper with error log fallback
        │   └── pii_sanitiser.py   # Truncation + regex redaction for prompt/response
        └── tests/
            ├── test_cc_pre_invoke.py
            ├── test_cc_post_invoke.py
            ├── test_pii_sanitiser.py
            ├── test_sdk.py
            ├── test_env_capture.py
            └── test_exporter.py
```
