# Workspace Guide

## Current Direction

This workspace is for the Paperclip-based build only.

The repo still contains an older Virtual Org prototype that talked about Tempa, Slack triage, and a broader automation plan. That older framing is legacy context. It should not guide new work unless a task explicitly says to preserve or migrate it.

## Working Rules

- Default to Paperclip-oriented work.
- Do not introduce new Tempa-specific assumptions.
- Do not hard-code a default target repo. Use `ALLOWED_REPOS` from `.env`.
- Prefer small cleanup and refactor changes that reduce confusion for future agents.
- If you touch legacy files, either make them generic or clearly mark them as legacy.

## What Is In This Repo

### Legacy Automation Harness

- `bot.py` listens for Slack messages and stores raw ideas.
- `triage.py` turns raw ideas into structured tasks.
- `worker.py` claims tasks, runs research, then runs implementation.
- `research.py` inspects a target repo and drafts an implementation plan.
- `implement.py` runs Claude Code in a local clone and opens a PR.

### Older Experiments

- `content_pipeline.py` and `models/content.py` are part of an older social content workflow.
- `prompts/` contains the LLM prompts used by the legacy harness.

## Safe Defaults

- Use `paperclip-feature` and `paperclip-bug` for new code-task categories.
- Keep support for older `tempa-feature` and `tempa-bug` rows only where it is cheap and harmless.
- Require an explicit repo allowlist before automated code changes run.

## Local Run

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python3 scripts/setup_db.py
.venv/bin/python3 bot.py
.venv/bin/python3 worker.py
```
