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

## Reusable Workflows And Shared Memory

This repo now has two simple durability layers so good work is not lost:

- Workflow recipes: saved task templates you can run again later
- Memory entries: prompts, plans, and decisions worth keeping

Why this matters:

- When something works once, you can save it as a recipe instead of recreating it from scratch.
- Research now pulls in relevant saved recipes and memory automatically when it plans a new task.
- Research also saves a compact plan and decision record back into shared memory, so useful thinking does not disappear into chat history.

Fastest path to value:

1. Save a workflow recipe once.
2. Start a new task from that recipe with a short request.
3. Let research reuse the saved context automatically.

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

Useful reusable-workflow endpoints:

- `POST /v1/workflows` saves or updates a reusable workflow recipe.
- `GET /v1/workflows` lists saved recipes.
- `POST /v1/workflows/{slug}/tasks` creates a new queued task from a saved recipe.
- `POST /v1/memory` saves a prompt, plan, or decision entry.
- `GET /v1/memory` lists saved memory entries.
- `POST /v1/sales/agents` creates a sales agent record.
- `POST /v1/sales/agents/{agent_id}/import` imports prospects for review and outreach.
- `POST /v1/sales/agents/{agent_id}/personalize` drafts outreach messages.
- `GET /v1/sales/agents/{agent_id}/dry-run-summary` previews dry-run send output.
- `POST /v1/sales/agents/{agent_id}/send-mode` changes an agent between dry-run and live mode.
- `POST /v1/sales/agents/{agent_id}/send` runs one sales-send worker pass.

Example: save a reusable workflow recipe

```bash
curl -X POST http://127.0.0.1:8080/v1/workflows \
  -H "Authorization: Bearer $CONTROL_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "slug": "founder-brief",
    "title": "Founder brief",
    "summary": "Turn rough notes into a short founder-ready brief.",
    "category": "ops",
    "task_title_template": "Write founder brief for {topic}",
    "task_description_template": "Create a concise brief for:\n{request}"
  }'
```

Example: create a task from that recipe

```bash
curl -X POST http://127.0.0.1:8080/v1/workflows/founder-brief/tasks \
  -H "Authorization: Bearer $CONTROL_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "request": "Summarize the latest customer calls into one page.",
    "variables": {"topic": "customer calls"}
  }'
```

## Keep The Control API Running 24/7

On a Linux server, use the included `systemd` service file. `systemd` is the built-in Linux process manager that starts services on boot and restarts them if they crash.

Service template:

- [deploy/systemd/virtual-org-control-api.service](deploy/systemd/virtual-org-control-api.service)

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

- [deploy/systemd/virtual-org-slack-dispatcher.service](deploy/systemd/virtual-org-slack-dispatcher.service)

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

- [docs/production-runbook.md](docs/production-runbook.md)
- [docs/paperclip-integration-spec.md](docs/paperclip-integration-spec.md) for the boundary between this control plane and the Paperclip UI

## Run The Tempa Sales Agent

The Tempa sales agent is a guarded outreach pipeline. It can import prospects, draft personalized messages, dry-run sends, then send live only after exact-message approval and safety checks.

Start the public preview, unsubscribe, and webhook API locally:

```bash
.venv/bin/python3 scripts/run_sales_public_api.py
```

Run one sales-send worker pass locally:

```bash
.venv/bin/python3 scripts/run_sales_worker.py <agent_id>
```

Important safety settings:

- `SALES_AGENT_ENABLED=true` must be set before any send worker can run.
- `SALES_SEND_MODE=live` and the agent's stored send mode must both be live before real email sends can happen.
- `SALES_KILL_SWITCH=true` stops sending immediately.
- A message must pass the deterministic checks, the LLM evaluation, and exact Slack approval before live send.

Use the full setup and recovery guide before production use:

- [docs/tempa-sales-agent-runbook.md](docs/tempa-sales-agent-runbook.md)

## Run The Worker

The worker is the small loop that moves queued tasks forward. Think of it like a clerk who picks the next item off the desk, works it one step forward, then comes back for the next one.

Process one available task and exit:

```bash
.venv/bin/python3 scripts/run_worker.py --once
```

Keep polling for more queued tasks:

```bash
.venv/bin/python3 scripts/run_worker.py --worker-id local-worker
```

Stop after a fixed number of claimed tasks:

```bash
.venv/bin/python3 scripts/run_worker.py --max-tasks 5
```

Important:

- The worker only touches tasks already stored in Postgres.
- It uses the same research and implementation pipeline as the rest of this repo.
- If a story needs manual verification, it stops and releases the task back into a waiting state.

## OpenClaw Chief Integration

The OpenClaw chief can now ask the control plane to advance one worker pass through the `studio_run_worker_once` tool exposed by the plugin in `openclaw/plugins/studio-control/`.

That trigger is asynchronous, which means it starts the work and returns immediately instead of holding the chief open until the whole pass finishes.

That means the chief can:

- check attention items
- check approvals
- trigger one safe worker pass
- report back only what changed

If a story is blocked on manual review, mark it complete with:

```bash
.venv/bin/python3 scripts/complete_manual_verification.py <task_id> --note "What you checked"
```

See [CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md) for the workspace rules agents should follow.
