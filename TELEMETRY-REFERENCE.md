# JPMC AI Platform — Telemetry System Reference

**Version:** 1.0.0  
**Status:** Built and verified end-to-end  
**Last updated:** March 2026  
**Owner:** JPMC AI Platform Team

---

## What This System Does

A zero-config AI observability system where the JPMC AI Platform team 
publishes skill packages to an internal marketplace. When any developer 
downloads a skill, unzips it, and runs one setup command, every future 
Claude Code conversation automatically emits OpenTelemetry traces to 
Jaeger — capturing who used the skill, in which project, what they asked, 
what the LLM responded, and how long it took — with PII fully redacted 
before any data leaves the developer's machine.

---

## Two Repos

| Repo | Owner | Purpose |
|------|-------|---------|
| `telemetry-v1` | Platform team | Skill package + telemetry layer. Published to marketplace. |
| `jpmc-skill-consumer` | Developer team | Sample developer project. Proves zero-config end-to-end. |

---

## Team Roles

### Platform Team — telemetry-v1

The platform team owns everything inside the skill package. Developers 
never see or touch any of this.

- Authors and maintains AI skills (SKILL.md prompt content)
- Owns the entire telemetry layer (hooks, _telemetry library, PII rules)
- Sets PII redaction patterns in telemetry.yaml
- Packages and publishes the zip via `./dist/build.sh`
- Monitors Jaeger for usage, errors, and prompt patterns across all teams
- Updates skills and telemetry silently by republishing the zip

### Developer Team — jpmc-skill-consumer

The developer does exactly four things. Nothing more is ever required.

1. Download `code-reviewer-1.0.0.zip` from JPMC AI marketplace
2. Unzip it anywhere on their machine
3. Run `python3 /path/to/code-reviewer-1.0.0/setup.py` from their project root
4. Restart Claude Code

From that point, every Claude Code conversation fires the telemetry 
hooks automatically. The developer never touches telemetry.yaml, never 
installs OTel packages, never edits settings.json.

---

## Skill Package Structure

This is what the zip contains and what lands in the developer's project 
after running setup.py.