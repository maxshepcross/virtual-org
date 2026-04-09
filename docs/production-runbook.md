# Production Runbook

This is the practical runbook for the live Virtual Org control stack on the remote server.

## What should be running

Two Linux background services should stay up at all times:

- `virtual-org-control-api`
- `virtual-org-slack-dispatcher`

OpenClaw should also be running through its own user service.

## Quick health check

Run these on the server:

```bash
systemctl status virtual-org-control-api
systemctl status virtual-org-slack-dispatcher
systemctl --user status openclaw-gateway
curl http://127.0.0.1:8080/health
```

Healthy looks like:

- both `virtual-org-*` services say `active (running)`
- `openclaw-gateway` says `active (running)`
- the health endpoint returns `{"status":"ok"}`

If `systemctl status` opens a viewer, press `q` to exit it.

## Restart commands

If something looks stuck, restart only the affected part.

Control API:

```bash
systemctl restart virtual-org-control-api
```

Slack dispatcher:

```bash
systemctl restart virtual-org-slack-dispatcher
```

OpenClaw gateway:

```bash
systemctl --user restart openclaw-gateway
```

## Live logs

These commands show live logs. Press `Ctrl + C` to stop them.

Control API:

```bash
journalctl -u virtual-org-control-api -f
```

Slack dispatcher:

```bash
journalctl -u virtual-org-slack-dispatcher -f
```

OpenClaw gateway:

```bash
openclaw logs
```

## Environment values that matter most

These live in `/root/virtual-org/.env`.

Important values:

- `DATABASE_URL`
- `CONTROL_API_TOKEN`
- `SLACK_BOT_TOKEN`
- `SLACK_DEFAULT_CHANNEL_ID`
- `SLACK_APPROVER_IDS`
- `SLACK_DISPATCH_INTERVAL_SECONDS`

After changing `.env`, restart the affected service.

## Safe approval modes

There are two approval modes:

Named approvers:

```env
SLACK_APPROVER_IDS=U12345,U67890
```

Wildcard approver mode:

```env
SLACK_APPROVER_IDS=*
```

Wildcard mode means any Slack user who reaches the approval flow can approve. That is convenient, but less safe.

## Smoke tests

### Attention smoke test

In OpenClaw chat:

```text
Use the studio_create_signal tool to create a high severity test signal with source "runbook-smoke-test", kind "smoke_test", severity "high", and summary "runbook smoke test".
```

Expected result:

- the attention item appears in the control plane
- the Slack dispatcher posts it into the founder Slack channel

### Approval smoke test

Create a task on the server:

```bash
cd /root/virtual-org
.venv/bin/python3 - <<'PY'
from config.env import load_project_env
load_project_env()
from models.task import create_task
task = create_task(
    idea_id=None,
    title="Approval smoke test",
    description="Temporary task for approval testing",
    category="ops",
    venture="virtual-org",
    requested_by="runbook",
    slack_channel_id="#virtual-org-chief",
)
print(task.id)
PY
```

Then create an approval:

```bash
cd /root/virtual-org
set -a
source .env
set +a
curl -i -X POST http://127.0.0.1:8080/v1/approvals \
  -H "Authorization: Bearer $CONTROL_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": TASK_ID_HERE,
    "action_type": "git_push",
    "target_summary": "approval smoke test"
  }'
```

Expected result:

- the API returns `201 Created`
- the dispatcher posts the approval into Slack

## Common gotchas

### Nothing happens after `journalctl -f`

You are still inside the live log stream. Press `Ctrl + C`.

### `systemctl status` seems stuck

You are inside the read-only viewer. Press `q`.

### `Missing bearer token`

You forgot to load `.env` into the current shell:

```bash
cd /root/virtual-org
set -a
source .env
set +a
```

### `Task X was not found`

Create a real smoke-test task first. Approval requests must belong to a real task.

### Slack dispatcher is running but nothing arrives in Slack

Check:

- `SLACK_BOT_TOKEN` is the current bot token
- the bot is actually in the Slack channel
- `SLACK_DEFAULT_CHANNEL_ID` matches the channel name or real channel ID
- dispatcher logs for Slack API errors

## Security reminders

- Rotate Slack tokens immediately if they are ever pasted into chat or logs.
- Wildcard approvers are convenient but broad.
- `tools.profile full` is useful for setup but should eventually be narrowed properly once plugin-tool visibility is understood.
