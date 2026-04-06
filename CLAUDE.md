# Workspace Guide

## Identity

This workspace belongs to AI Venture Studio.

It is a studio operations repo, not the default product repo. Its job is to coordinate work across multiple businesses and codebases without guessing where code should be changed.

## Non-Negotiable Rules

- Never assume this repo is the target for product feature work.
- Only change another codebase when that repo is explicitly named and present in `ALLOWED_REPOS`.
- If the task is unclear about which repo or workspace should be changed, stop and ask instead of guessing.
- Keep the distinction clear between:
  - this workspace, which holds studio automation and routing logic
  - target repos, which hold the actual product code

## What This Repo Contains

- `research.py` to create implementation plans for studio tasks
- `implement.py` to execute approved changes in an explicit target repo
- `config/` for model choices, timing defaults, environment loading, and the explicit repo allowlist
- `models/task.py` for the Postgres-backed task queue, leases, heartbeats, and event log
- `services/github_ops.py` for branch creation and PR opening
- `prompts/research.md` for the structured research prompt template
- `scripts/setup_db.py` for the minimal task database schema
- `tests/` for regression coverage around environment loading, timeouts, branch creation, and research prompt handling

## Removed On Purpose

- Legacy intake flows
- Legacy notification plumbing
- Content interview and draft pipelines
- Background launchd scripts tied to that legacy workflow

Do not reintroduce those systems unless a future task explicitly asks for them.

## Safe Defaults

- Treat this repo as the control plane for the studio.
- Require an explicit repo allowlist before any automated code change runs.
- Treat `.repos/` as a cache of cloned target repos, not as part of this workspace's source of truth.
- Expect task state to live in Postgres via `DATABASE_URL`, not in flat files.
- Prefer generic language like "task", "target repo", and "studio" over product-specific assumptions.
- Keep documentation blunt and unambiguous so new agents do not confuse workspace identity with product identity.

## Environment

- `.env` should provide `DATABASE_URL` for the task queue database.
- `.env` should provide `ALLOWED_REPOS` as a comma-separated allowlist of repos this workspace may touch.
- API and GitHub credentials should be loaded from `.env` and never hardcoded in source.

## Local Run

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python3 scripts/setup_db.py
.venv/bin/python3 -m unittest discover -s tests
```
