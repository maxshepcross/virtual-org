# Agent Guide

## Repo Identity

This repo is the AI Venture Studio control plane.

It is for studio-wide task routing, research, implementation handoff, and repo safety rules. It is not the default place to build product features.

## Hard Rules

- Never assume this repo is the right place for product work.
- Only change another codebase when the task names that repo explicitly and the repo is present in `ALLOWED_REPOS`.
- If the task does not clearly name the repo to change, stop and ask instead of guessing.
- Keep the difference clear between this control repo and any target repo cloned under `.repos/`.

## What Lives Here

- `research.py` builds structured implementation plans for studio tasks.
- `implement.py` runs approved work in an explicit target repo and opens a PR.
- `config/` holds shared settings such as model names, timeouts, env loading, the repo allowlist, and studio policy files.
- `models/task.py` stores queued task state in Postgres, including leases, heartbeats, event history, and per-story execution state.
- `services/github_ops.py` contains guarded branch, commit, push, and PR helpers.
- `prompts/` defines the research, PRD, and task-breakdown prompt formats.
- `scripts/setup_db.py` creates the minimal task database schema.
- `tests/` covers the core safety and regression cases.

## Safe Defaults

- Use plain terms like "task", "target repo", and "studio".
- Keep changes focused and avoid reviving removed legacy systems unless a task explicitly asks for them.
- Treat `.repos/` as disposable local clones used for research and implementation, not as first-class workspace code.
- Load secrets and repo allowlists from `.env`, never from hardcoded values.

## Local Setup

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python3 scripts/setup_db.py
.venv/bin/python3 -m unittest discover -s tests
```

If a task is waiting on manual verification, complete that handoff with:

```bash
.venv/bin/python3 scripts/complete_manual_verification.py <task_id> --note "What you checked"
```
