# Agent Stack Blueprint

This file captures the parts worth borrowing from `clawchief`, `ralph`, and `ai-dev-tasks` for the AI Venture Studio control plane.

Use these repos as pattern libraries, not as direct dependencies.

## Recommended Position

Use this repo as the system of record for:

- task queue state
- repo allowlists and safety rules
- research and implementation handoff
- branch and PR automation

Add selected patterns from the three external repos around that foundation.

Do not replace the Postgres task queue with markdown files.
Do not replace explicit repo targeting with free-form agent autonomy.
Do not copy personal chief-of-staff workflows into the studio control plane.

## What To Take From `clawchief`

Borrow these ideas:

- A clear policy layer separate from execution.
- One short heartbeat document that says what to check and in what order.
- Separate files for priority rules, auto-resolution rules, and recurring routines.
- A rule that the agent should update the real source of truth in the same turn it acts.
- Very short recurring prompts, with the detailed logic living in reusable skills or playbooks.

Adapt them for this repo like this:

- Create a studio priority map for deciding which queued tasks deserve immediate work.
- Create an auto-resolution policy for when the system can safely route, research, retry, or fail a task without human approval.
- Create a studio heartbeat document for recurring work such as lease cleanup, stale task recovery, PR status refresh, and queue nudges.

Do not copy these parts directly:

- inbox, calendar, travel, and founder executive-assistant flows
- Gmail-specific or meeting-note-specific routines
- markdown task files as the main source of truth

## What To Take From `ralph`

Borrow these ideas:

- Fresh context each run. Each implementation pass should start clean instead of carrying too much old conversation state.
- Small task units. A worker should attempt one small story at a time, not an entire feature at once.
- Explicit pass/fail state per story.
- Acceptance criteria attached to each story.
- Append-only progress notes so later runs can learn from earlier runs.
- Archive old runs when a new branch or feature starts.
- Verification gates for browser checks, tests, and type checks before marking work complete.

Adapt them for this repo like this:

- Add a structured implementation-plan format with small stories, acceptance criteria, and a per-story status field.
- Add a progress log to each task record so workers can leave short notes for the next worker.
- Add a loop mode that executes one story per run and stops if checks fail.
- Keep branch creation and PR opening in guarded Python services, not inside a shell-only loop.

Do not copy these parts directly:

- `--dangerously-skip-permissions` style fully open execution
- a bash-only orchestrator as the long-term control plane
- automatic edits to `AGENTS.md` after every run

## What To Take From `ai-dev-tasks`

Borrow these ideas:

- Start with a short PRD, which is a plain-English feature brief.
- Ask only the few clarifying questions that materially change the work.
- Break work into high-level tasks before generating detailed sub-tasks.
- Show relevant files up front so the worker knows where to look.
- Keep a checklist so progress is visible and reviewable.

Adapt them for this repo like this:

- Add a PRD prompt template for studio tasks that need more shaping before implementation.
- Add a task-breakdown prompt template that turns a PRD or research result into small executable stories.
- Store suggested files to read or modify in structured research output, not just free text.

Do not copy these parts directly:

- mandatory manual pauses for every task phase
- branch creation as a task-list item, because this repo already handles branch creation safely
- markdown files in `/tasks` as the canonical task system for studio operations

## Recommended Build Order

1. Add a studio heartbeat policy and auto-resolution policy under `config/`.
2. Add two new prompt templates under `prompts/`: one for PRDs and one for task breakdown.
3. Extend research output so it can return small stories with acceptance criteria, priority, and candidate files.
4. Extend the task model to store progress notes and per-story status.
5. Add an implementation mode that executes one story at a time and records verification results.

## First Version To Build

The best low-risk first version is:

- keep Postgres as the source of truth
- keep explicit target-repo allowlists
- keep Python services for git and PR operations
- add better planning inputs from `ai-dev-tasks`
- add better execution chunking and verification from `ralph`
- add policy and heartbeat files from `clawchief`

That gives you a safer control tower with better task shaping and smaller agent work units, without turning this repo into a personal assistant system or a shell-script experiment.

## Decision Summary

Use `clawchief` for operating rules.
Use `ralph` for execution-loop patterns.
Use `ai-dev-tasks` for planning templates.

Keep this repo's current strengths:

- Postgres-backed task state
- explicit repo targeting
- guarded branch and PR helpers
- a clean separation between research and implementation
