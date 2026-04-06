# AI Venture Studio Workspace

This repo is the control room for AI Venture Studio.

Use it for studio-wide automation, task routing, repo handoff rules, and shared operational code. Do not treat it as the default place to build product features.

## Build Location Rule

- If a task is about a product, client app, or business-specific codebase, work in an explicitly named target repo from `ALLOWED_REPOS`.
- If a task is about studio operations, repo routing, automation, or documentation for this workspace, work here.
- If the task does not clearly say which repo or workspace to change, stop and ask. Do not guess.

## What Lives Here

- `research.py` for turning a studio task into an implementation plan
- `implement.py` for applying a plan in an explicitly allowed target repo
- `models/task.py` for queued task storage and leasing
- `services/github_ops.py` for safe branch and PR helpers

## What Does Not Live Here

- Product feature work by default
- Legacy intake flows
- Legacy content pipeline logic

Those old systems were removed on purpose so future agents do not confuse this workspace with an old prototype.

## Local Setup

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python3 scripts/setup_db.py
```

## Verification

Run the test suite with:

```bash
.venv/bin/python3 -m unittest
```

See [CLAUDE.md](CLAUDE.md) for the workspace rules agents should follow.
