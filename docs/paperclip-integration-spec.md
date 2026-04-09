# Paperclip Integration Spec

This note defines the clean split between Paperclip and this repo.

The short version:

- This repo is the engine.
- Paperclip is the cockpit.

Paperclip should let Max see what is happening, understand why it is happening, and steer the system without becoming a second control plane with its own private state.

## Goal

Keep the agentic logic in this repo, but make it visible and manageable in Paperclip.

That means:

- tasks still live here
- runs still live here
- approvals still live here
- policy decisions still live here
- Paperclip reads and controls those records through the API

## Non-Goal

Paperclip should not build its own queue, approval model, or run-history model.

If Paperclip starts storing a second copy of task state as if it were the source of truth, the system will split into two brains. That is exactly what we want to avoid.

## Source Of Truth

Paperclip should treat these objects from this repo as the source of truth:

1. `Task`
2. `AgentRun`
3. `ApprovalRequest`
4. `AttentionItem`
5. `PolicyDecision`

The stable user-facing IDs should be:

- `task.id` for the business job
- `agent_runs.run_key` for one concrete execution attempt

In plain English:

- the task is the job
- the run is one try at doing the job

## Boundary

### This Repo Owns

- task queue and leasing
- worker passes
- research and implementation logic
- branch and PR creation
- policy checks
- approvals
- Slack delivery
- durable run history

### Paperclip Owns

- visualization
- filtering
- drill-down views
- approval UI
- retry and resume controls
- manual verification controls
- founder-facing dashboards

### Rule

Paperclip can issue commands.

This repo executes them and records the result.

Paperclip displays the result.

## Existing API Surface

These control-plane endpoints already exist and are enough to build the first read-only dashboard plus a small set of controls:

### Read Endpoints

- `GET /health`
  - Simple liveness check.
- `GET /v1/attention`
  - Founder-facing alerts, failures, and approval-needed items.
- `GET /v1/approvals/pending`
  - Current unresolved approvals.
- `GET /v1/tasks`
  - Task list for the control room and filtered queues.
- `GET /v1/tasks/{task_id}/state`
  - Full task detail, including attention items, approvals, policy decisions, and agent runs.
- `GET /v1/agent-runs`
  - Run list for the timeline, worker monitor, and task drill-down.

### Write Endpoints

- `POST /v1/tasks`
  - Create a new task when Paperclip should originate work directly.
- `POST /v1/worker/run-once`
  - Starts one background worker pass.
- `POST /v1/tasks/{task_id}/manual-verification/complete`
  - Continue a task after a human has checked the blocked story.
- `POST /v1/tasks/{task_id}/requeue`
  - Requeue a blocked or failed task for another worker pass.
- `POST /v1/approvals/{approval_id}/resolve`
  - Approve or deny a risky action.
- `POST /v1/agent-runs`
  - Create a durable run record.
- `PATCH /v1/agent-runs/{run_id}`
  - Update run status and metadata.
- `POST /v1/agent-runs/{run_id}/artifacts`
  - Append artifacts such as summaries, verification results, errors, or PR links.

## API Gaps To Close

Paperclip now has the main control-room endpoints it needs. The remaining gaps are about polish, live updates, and worker visibility rather than basic operability.

### Nice To Have Next

- `GET /v1/workers`
  - Show worker heartbeat, current lease, and last result.
- `GET /v1/briefings/latest`
  - Show the newest founder digest in Paperclip.
- WebSocket or SSE stream
  - Push live updates into Paperclip without polling.

## Paperclip Screens

Paperclip should start with five screens.

### 1. Control Room

This is the front page.

It should show:

- queued tasks
- blocked tasks
- failed tasks
- pending approvals
- latest worker result
- latest high-severity attention items

Top actions:

- `Run one worker pass`
- `Open approval queue`
- `Open blocked tasks`

### 2. Task Detail

This is the "what is happening on this job?" page.

It should show:

- task title, venture, repo, requester
- task status
- current story ID
- branch name
- PR URL
- progress notes
- verification log
- attention items
- approvals
- linked runs

Top actions:

- `Run worker pass`
- `Requeue task`
- `Mark manual verification complete`
- `Open PR`
- `Open Slack thread`

### 3. Run Detail

This is the "what happened during this execution attempt?" page.

It should show:

- run key
- task ID
- parent run ID
- run kind
- trigger source
- who triggered it
- status
- branch name
- PR URL
- Slack route
- artifacts
- error message
- last heartbeat

This page matters because it turns the agent system into something reviewable instead of mystical.

### 4. Approval Queue

This is the founder control panel for risky actions.

It should show:

- approval ID
- action type
- task
- run
- target summary
- when requested
- current Slack thread

Top actions:

- `Approve`
- `Deny`
- `Open task`
- `Open run`

### 5. Attention Feed

This is the incident and alerts page.

It should show:

- severity
- headline
- recommended action
- task
- run
- bucket
- Slack posting status

Top actions:

- `Open task`
- `Open run`
- `Open Slack thread`

## First Control Actions

Paperclip should not start with every button imaginable.

It should start with the controls that are both high-value and low-risk.

### Phase 1 Controls

1. Run one worker pass
2. Approve an action
3. Deny an action

### Phase 2 Controls

4. Mark manual verification complete
5. Requeue a blocked or failed task

### Phase 3 Controls

6. Create a new task
7. Retry a specific run
8. Pause or disable a worker

## Recommended Polling Model

Paperclip does not need real-time streaming on day one.

Start with polling:

- control room: every 5 to 10 seconds
- approval queue: every 5 seconds
- task detail: every 5 seconds while open
- run detail: every 5 seconds while open

That is enough to make the system feel live without building a full event stream first.

## Data Mapping

Paperclip UI terms should map directly to control-plane terms.

Do not invent new names if the existing names are already clear.

| Paperclip label | Control-plane object |
| --- | --- |
| Task | `Task` |
| Run | `AgentRun` |
| Approval | `ApprovalRequest` |
| Alert | `AttentionItem` |
| Policy decision | `PolicyDecision` |

This sounds small, but it matters. Shared language is what keeps the dashboard and backend feeling like one system.

## Suggested Paperclip Rollout

### Phase 1: Read-Only Cockpit

Build:

- control room
- task detail
- run detail
- approval queue
- attention feed

Use only existing read endpoints plus `POST /v1/worker/run-once`.

Success condition:

Max can open Paperclip and answer:

- what is blocked?
- what is running?
- what needs my approval?
- which run created this PR?

### Phase 2: Basic Steering

Add:

- approve / deny buttons
- manual verification complete button
- requeue button

Success condition:

Max no longer needs shell scripts for normal operational steering.

### Phase 3: Full Founder's Cockpit

Add:

- task creation
- worker health view
- run filtering and search
- richer artifact rendering
- source-system panels for Paperclip, Slack, Stripe, PostHog, Xero, or others

Success condition:

Paperclip becomes the place Max uses to see and steer the studio, while this repo remains the execution engine.

## Definition Of Done

This integration is successful when:

1. Paperclip does not own duplicate task or run state.
2. Every visible Paperclip item links back to one task or run in this repo.
3. Max can approve, retry, and continue normal work from Paperclip.
4. The chief, Slack, and Paperclip all point at the same durable run records.
5. No one needs to guess whether the source of truth is Paperclip or the control plane.

## Bottom Line

The right shape is not "Paperclip or this repo."

The right shape is:

- this repo does the work
- Paperclip shows the work
- Paperclip steers the work
- this repo remains the source of truth
