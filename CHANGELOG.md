# Changelog

## 0.1.10 - 2026-04-09

### Added

- Added a real Slack agent layer with signed Slack event endpoints, interactivity handling, founder command routing, and AI-surface helpers for titles, loading states, and suggested prompts.
- Added approval buttons to Slack approval messages so founder approvals can now be resolved directly inside Slack instead of only through the control API.
- Added a Slack app manifest and a short setup guide so the new agent can be configured in Slack without hunting through docs.
- Added a Caddy reverse-proxy template and public API URL setup guide so Slack can reach the local control API over HTTPS.
- Added regression tests for Slack event verification, Slack interactivity parsing, founder command handling, and richer Slack delivery formatting.

### Changed

- Split Slack Web API calls into a shared client so the always-on dispatcher and the new Slack agent use the same Slack transport layer.

## 0.1.9 - 2026-04-09

### Added

- Added `docs/spectre-patterns.md`, a short architecture note on what Puebla should borrow from Harvey's Spectre model and a concrete five-step roadmap for this control plane.
- Added richer durable run records with stable run keys, trigger metadata, branch and PR fields, Slack routing, artifact summaries, and stronger audit fields across the control-plane schema and models.

### Changed

- Threaded run records through the research loop, implementation loop, control API, approval flow, Slack delivery, and policy-signal routing so one run can be tracked cleanly across the whole system.
- Changed implementation handoffs so worker-friendly queue releases are preserved while run history still captures approvals, manual checks, pushes, verification, and PR outcomes.

### Fixed

- Fixed upgraded databases so `run_key` values are backfilled and enforced as required instead of staying silently nullable.
- Fixed implementation failure cleanup so a branch setup error marks the run failed instead of leaving a fake "running" record behind.

## 0.1.8 - 2026-04-09

### Added

- Added a worker loop and CLI so queued tasks can now move forward automatically instead of waiting for a human to kick each step.
- Added a chief-to-worker trigger so the OpenClaw chief can start one safe background worker pass without blocking the conversation.
- Added agent-run tracking for worker phases so the control plane can record who is working on what and when it last checked in.

### Changed

- Changed research so rough requests are shaped into a brief and a small task breakdown before the final implementation plan is produced.
- Updated the README and chief workspace instructions so local worker runs and chief-triggered worker passes are documented alongside the control API and Slack services.

### Fixed

- Fixed implementation handoffs so tasks are released back to the queue, to approval, or to manual verification cleanly instead of getting stuck on a worker lease.
- Fixed delivery safety so chief-triggered runs now respect the server-side push approval rule before code is delivered.
- Fixed the worker trigger endpoint so it starts in the background and returns immediately, keeping the chief responsive.

## 0.1.7 - 2026-04-09

- Fixed `scripts/run_api.py` so it can start cleanly on a server without the `PYTHONPATH=...` workaround.
- Added a Linux `systemd` service template for keeping the control API running 24/7 and restarting it automatically after crashes or reboots.
- Updated the README with a simple “run the API” and “keep it running” section for the remote OpenClaw box.
- Added default Slack-route fallback logic so new attention items and approval requests can target a founder channel even when a task does not already have its own Slack route.
- Added an always-on Slack dispatcher service that posts new attention items and pending approval requests to Slack, stores delivery markers, and reuses task threads to avoid duplicate founder notifications.
- Added a practical production runbook covering service health checks, restart commands, smoke tests, and common failure recovery steps for the remote OpenClaw box.

## 0.1.5 - 2026-04-08

- Added the first control-plane foundation for the remote OpenClaw architecture: new Postgres tables for agent runs, signals, attention items, approvals, policy decisions, network requests, briefings, and Slack routes.
- Added a small internal FastAPI app in `api/app.py` plus service modules for policy evaluation, approval handling, signal bucketing, and founder briefings.
- Added default policy config files for approval and network decisions, extended the task model with Slack and approval fields, and expanded the schema tests to cover the new control-plane tables.
- Added regression tests for the policy engine, signal routing, and the new API endpoints, and updated `requirements.txt` for the API runtime dependencies.

## 0.1.4 - 2026-04-07

- Extended the task schema and model with per-story execution state, progress notes, verification logs, and current story tracking.
- Refactored `implement.py` to execute one story at a time, reuse branches safely, record verification results, and only open a PR after all stories are complete.
- Added regression tests for branch reuse, task JSON parsing, story selection, implementation helpers, and the database schema upgrade path.
- Fixed review findings so manual verification blocks story completion, push failures return truthful errors, and `pr_open` is treated as a final task state.
- Added `scripts/complete_manual_verification.py` plus task-model support so a human can unblock a manually reviewed story and let the loop continue cleanly to the next story or PR creation.

## 0.1.3 - 2026-04-07

- Added studio policy files in `config/` plus new `prompts/create_prd.md` and `prompts/task_breakdown.md`.
- Upgraded `research.py` and `prompts/research.md` so research output can include small executable stories with acceptance criteria and verification steps.
- Updated repo docs so the new policy and prompt files are part of the documented control-plane shape.

## 0.1.2 - 2026-04-07

- Added `docs/agent-stack-blueprint.md` to capture which patterns to borrow from `clawchief`, `ralph`, and `ai-dev-tasks` for the studio control plane.

## 0.1.1 - 2026-04-06

- Refreshed the workspace guidance in `CLAUDE.md`, `README.md`, and a new root `AGENTS.md` so the docs match the current repo structure, repo-targeting rules, and real test command.

## 0.1.0 - 2026-04-06

- Reframed the repo as the AI Venture Studio control plane instead of a product workspace.
- Removed the legacy intake, notification, and content pipeline code.
- Simplified the task schema, repo-targeting rules, and safer branch creation behavior.
