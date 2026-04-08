# Changelog

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
