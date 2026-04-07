# Studio Auto-Resolution Policy

Purpose: define when the control plane can act automatically and when it should stop.

This file is the decision layer for action.

## Resolution Modes

- `auto_resolve`
  Safe to act without asking.
- `draft_and_review`
  The likely next step is clear, but a human should confirm the decision or wording.
- `escalate`
  Too much risk, ambiguity, or missing authority to proceed safely.
- `archive`
  Low-value noise or duplicate work.

## Safe Auto-Resolve Lane

Auto-resolve only when all of these are true:

- the target repo is explicit or the work clearly belongs in this repo
- the next action is operational, not strategic
- success can be verified with tests or other checks
- a mistake would be low-cost and easy to correct

Examples:

- enrich a research plan
- classify and route a task
- refresh cloned repo context
- fail a stale lease
- open a PR after successful checks
- update docs that describe the control plane itself

## Draft-And-Review Lane

Use this when:

- the task changes product scope materially
- the task spans multiple repos or business units
- the user intent is clear but the chosen shape is still debatable

## Escalate Lane

Use this when:

- the target repo is missing or disallowed
- the change affects security, billing, or legal claims without enough context
- the task conflicts with repo identity or safety rules
- verification is impossible with the available environment

## Source-Of-Truth Rule

Do not act from memory alone.
Ground actions in:

- the queued task record
- the explicit target repo
- the repo allowlist
- the current codebase state
- test or verification output
