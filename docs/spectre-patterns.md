# Spectre Patterns For Puebla

This note captures what looks worth borrowing from Harvey's Spectre write-up for this repo.

The goal is not to copy Harvey's system. The goal is to sharpen Puebla as a studio control plane for durable, reviewable agent work.

## Why This Matters

The Spectre article validates the direction this repo is already taking.

Puebla already has some of the same foundations:

- a durable task record in `models/task.py`
- lease-based work claiming and heartbeats
- append-only event history and progress notes
- per-story execution state and verification logs
- guarded branch and PR helpers

The article is useful because it shows which parts are likely to matter most as this system grows.

## Patterns Worth Borrowing

### 1. The durable object should be the run, not the worker

The temporary machine doing the work should be disposable.

The important thing is the long-lived record that stores:

- who asked for the work
- what context was attached
- what happened during execution
- what artifacts came out
- what still needs review

For Puebla, this means the control plane should keep treating the database record as the source of truth, not the live process.

### 2. Every surface should point at the same record

Slack, the API, scheduled jobs, and pull requests should all refer back to one shared object.

That avoids the common failure mode where each surface creates its own half-private session and the real story gets split across places.

### 3. Scheduled work should use the same runtime as human-triggered work

Recurring cleanup, verification, retries, dependency checks, and branch hygiene should appear as ordinary runs with ordinary history.

That keeps automation visible and reviewable instead of creating a hidden second system.

### 4. Security comes from explicit boundaries

The article's strongest point is that agent security cannot rely on "whatever the engineer's machine already has access to."

For Puebla, the practical lesson is:

- keep target repos explicit
- keep credentials short-lived and scoped where possible
- keep tool access injected per run
- keep durable state changes going through the control plane

In plain English: the agent can work inside its box, but it should not get the master keys to the whole building.

### 5. Not every run should end in code

Some jobs should end with:

- an investigation summary
- a proposed plan
- a risk review
- a verification report
- a branch and PR

That matters because this repo is a control tower, not just a code-writing bot wrapper.

## Patterns To Avoid Copying Blindly

- Do not overbuild enterprise complexity before it is needed.
- Do not collapse product execution and control-plane orchestration into one repo.
- Do not assume background cloud agents replace local workflows in every case.
- Do not let "shared context" become vague ambient access. Shared must still mean scoped and auditable.

## Concrete Puebla Roadmap

### 1. Add a first-class run record

Today, `Task` carries both planning state and execution history.

That is workable for now, but the clearer long-term shape is:

- `Task` = the business job to be done
- `Run` = one concrete execution attempt against that task

That split would make retries, resumability, follow-ups, and scheduled re-runs much cleaner.

### 2. Unify Slack, API, and PR activity around one run ID

A run should have one stable ID that appears in:

- Slack thread updates
- API responses
- approval requests
- branch metadata
- PR bodies or comments

That makes handoff easier because everyone is looking at the same piece of work.

### 3. Treat automations as normal runs

When this repo grows recurring routines, such as stale-task recovery or verification sweeps, those should create ordinary runs with the same logs and review surface as manual work.

### 4. Tighten the execution boundary

Before adding more tools, make the rules clearer for what a worker can access during a run.

Priority areas:

- explicit tool bundles per run
- stronger separation between repo access and control-plane state
- better audit fields for who triggered, approved, and completed a run

### 5. Expand artifact types beyond code changes

The system should treat these as first-class outputs:

- summaries
- plans
- risk flags
- verification results
- diffs, branches, and PRs

That would make Puebla more useful for research, triage, and founder visibility, not just implementation.

## Recommended Order

If we use this note as an execution guide, the safest order is:

1. Add a `Run` model and schema.
2. Thread run IDs through Slack and API flows.
3. Make scheduled routines create normal runs.
4. Tighten run-scoped tool and credential boundaries.
5. Expand artifact typing and review surfaces.

## Bottom Line

The article does not suggest a new direction. It confirms the right one.

Puebla should keep moving toward a durable, inspectable control plane where workers are disposable, history is shared, permissions are explicit, and every meaningful agent action leaves behind something a human can review.
