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
- `config/` for model settings, timing defaults, env loading, the repo allowlist, and studio policy files
- `models/task.py` for Postgres-backed task storage, leasing, heartbeats, event history, and per-story execution state
- `services/github_ops.py` for safe branch and PR helpers
- `prompts/` for research, PRD, and task-breakdown prompt templates
- `scripts/setup_db.py` for creating the task database schema
- `tests/` for regression coverage around env loading, timeouts, branch creation, and research prompt handling

## What Does Not Live Here

- Product feature work by default
- Legacy intake flows
- Legacy content pipeline logic

Those old systems were removed on purpose so future agents do not confuse this workspace with an old prototype.

## Local Setup

This project expects a local Python environment, which is an isolated box for its dependencies, plus a `.env` file for secrets and repo rules.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python3 scripts/setup_db.py
```

Important `.env` values:

- `DATABASE_URL` points to the Postgres database used for queued tasks.
- `ALLOWED_REPOS` is a comma-separated allowlist of repos this workspace may change.
- `ANTHROPIC_API_KEY` and `GITHUB_TOKEN` should be set in `.env`, never hardcoded in source.
- `SLACK_DEFAULT_CHANNEL_ID` is the fallback Slack channel for founder-facing alerts when a task does not already have its own Slack route.
- `SLACK_BOT_TOKEN` is the Slack bot token used by the always-on dispatcher to post alerts and approval requests.
- `SLACK_DISPATCH_INTERVAL_SECONDS` controls how often the dispatcher checks for new items to post.

## Verification

Run the test suite with:

```bash
.venv/bin/python3 -m unittest discover -s tests
```

## Run The Control API

The control API is the small internal web service that OpenClaw talks to.

For local development:

```bash
.venv/bin/python3 scripts/run_api.py
```

The API listens on `127.0.0.1:8080` by default and exposes a simple health check at:

```text
http://127.0.0.1:8080/health
```

## Keep The Control API Running 24/7

On a Linux server, use the included `systemd` service file. `systemd` is the built-in Linux process manager that starts services on boot and restarts them if they crash.

Service template:

- [deploy/systemd/virtual-org-control-api.service](/Users/maxshepherd-cross/conductor/workspaces/virtual-org/washington-v1/deploy/systemd/virtual-org-control-api.service)

Typical install steps on the server:

```bash
cp deploy/systemd/virtual-org-control-api.service /etc/systemd/system/virtual-org-control-api.service
systemctl daemon-reload
systemctl enable --now virtual-org-control-api
systemctl status virtual-org-control-api
```

Useful follow-up commands:

```bash
journalctl -u virtual-org-control-api -f
curl http://127.0.0.1:8080/health
```

## Keep Slack Notifications Running 24/7

Founder-facing Slack delivery now uses a small dispatcher service. It checks for new attention items and approval requests, posts them into Slack, and marks them as posted so they are not repeated.

Service template:

- [deploy/systemd/virtual-org-slack-dispatcher.service](/Users/maxshepherd-cross/conductor/workspaces/virtual-org/washington-v1/deploy/systemd/virtual-org-slack-dispatcher.service)

Typical install steps on the server:

```bash
cp deploy/systemd/virtual-org-slack-dispatcher.service /etc/systemd/system/virtual-org-slack-dispatcher.service
systemctl daemon-reload
systemctl enable --now virtual-org-slack-dispatcher
systemctl status virtual-org-slack-dispatcher
```

Useful follow-up commands:

```bash
journalctl -u virtual-org-slack-dispatcher -f
```

For the full production checklist, restart commands, smoke tests, and common recovery steps, use:

- [docs/production-runbook.md](/Users/maxshepherd-cross/conductor/workspaces/virtual-org/washington-v1/docs/production-runbook.md)

If a story is blocked on manual review, mark it complete with:

```bash
.venv/bin/python3 scripts/complete_manual_verification.py <task_id> --note "What you checked"
```

See [CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md) for the workspace rules agents should follow.
