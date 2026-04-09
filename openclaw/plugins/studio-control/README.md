# Studio Control OpenClaw Plugin

This plugin is the bridge between a remote OpenClaw gateway and the Python control API in this repo.

It does two jobs:
- gives the chief and worker agents a few control-plane tools
- intercepts risky tool calls and asks the control API whether they should be allowed, blocked, or approval-gated

## Expected config

Add the plugin to your OpenClaw gateway config and pass:

```json
{
  "plugins": {
    "enabled": true,
    "load": {
      "paths": [
        "/opt/venture-studio/openclaw/plugins/studio-control"
      ]
    },
    "entries": {
      "studio-control": {
        "enabled": true,
        "config": {
          "controlApiBaseUrl": "https://control.internal",
          "controlApiToken": "change-me"
        }
      }
    }
  }
}
```

## Tools exposed

- `studio_attention`
- `studio_tasks`
- `studio_task_state`
- `studio_create_task`
- `studio_pending_approvals`
- `studio_create_signal`
- `studio_complete_manual_verification`
- `studio_requeue_task`
- `studio_agent_runs`
- `studio_recent_briefings`
- `studio_generate_briefing`
- `studio_run_worker_once`

Approval resolution should happen through real Slack interactions, where Slack proves which person clicked approve or deny.

## Hook behavior

The `before_tool_call` hook maps risky tool calls into control-plane policy checks.
If the control API returns:

- `allow`: tool call continues
- `require_approval`: OpenClaw pauses and asks for approval
- `block`: tool call is stopped before execution
