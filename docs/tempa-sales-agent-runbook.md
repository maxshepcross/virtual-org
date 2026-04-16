# Tempa Sales Agent Runbook

This is the safe operating guide for the Tempa Sales Agent.

The sales agent has two production parts:

- `virtual-org-sales-public-api`: public preview pages, unsubscribe pages, and AgentMail webhooks.
- `virtual-org-sales-worker`: the background sender that prepares or sends outreach.

Think of the public API as the shop front and the worker as the person in the back room sending letters.

## Safety Defaults

Live email is off unless all of these are true:

- `SALES_AGENT_ENABLED=true`
- `SALES_SEND_MODE=live`
- `SALES_KILL_SWITCH=false`
- the first-live approval has been approved in Slack
- the sender is verified and healthy
- the prospect is not suppressed
- the message passed the sales quality checks

For the first rollout, keep:

```env
SALES_SEND_MODE=dry_run
SALES_KILL_SWITCH=true
SALES_DAILY_NEW_PROSPECT_LIMIT=5
```

Dry-run mode prepares the emails without sending them. It is the rehearsal before opening night.

## Required Environment Values

These live in `/opt/virtual-org/.env` on the server.

```env
DATABASE_URL=
CONTROL_API_TOKEN=
CONTROL_PUBLIC_BASE_URL=

APOLLO_API_KEY=
AGENTMAIL_API_KEY=
AGENTMAIL_SENDER_DOMAIN=
AGENTMAIL_WEBHOOK_SECRET=

TEMPA_SALES_STRATEGY_URL=
TEMPA_SALES_STRATEGY_ALLOWED_HOSTS=
TEMPA_SALES_STRATEGY_TOKEN=
TEMPA_DEMO_BOOKING_URL=
SALES_SENDER_NAME=Max
SALES_POSTAL_ADDRESS=
SALES_UNSUBSCRIBE_BASE_URL=

SALES_AGENT_ENABLED=false
SALES_SEND_MODE=dry_run
SALES_KILL_SWITCH=true
SALES_AGENT_ID=CHANGE_ME
SALES_DAILY_NEW_PROSPECT_LIMIT=5
SALES_ALLOWED_RECIPIENT_COUNTRIES=US
SALES_WORKER_POLL_INTERVAL_SECONDS=60
SALES_PUBLIC_API_HOST=127.0.0.1
SALES_PUBLIC_API_PORT=8091
SALES_WEBHOOK_MAX_BODY_BYTES=262144
```

Use HTTPS for `CONTROL_PUBLIC_BASE_URL`, `TEMPA_SALES_STRATEGY_URL`, `TEMPA_DEMO_BOOKING_URL`, and `SALES_UNSUBSCRIBE_BASE_URL`. `TEMPA_SALES_STRATEGY_TOKEN` is sent to Tempa as `X-Internal-Token`.

## Install The Services

Run these on the server after deploying the code to `/opt/virtual-org`.

Create the low-privilege service user:

```bash
useradd --system --home /opt/virtual-org --shell /usr/sbin/nologin virtual-org
chown -R root:root /opt/virtual-org
chown root:virtual-org /opt/virtual-org/.env
chmod 640 /opt/virtual-org/.env
```

The service user can read the app and environment file, but it cannot rewrite the code. That keeps a public API compromise from becoming a permanent server compromise.

Run the database setup before starting services:

```bash
cd /opt/virtual-org
.venv/bin/python3 scripts/setup_db.py
```

Install the systemd service files:

```bash
cp /opt/virtual-org/deploy/systemd/virtual-org-sales-public-api.service /etc/systemd/system/
cp /opt/virtual-org/deploy/systemd/virtual-org-sales-worker.service /etc/systemd/system/
systemctl daemon-reload
```

Set `SALES_AGENT_ID` in `/opt/virtual-org/.env` to the real sales agent ID before starting the worker. The worker fails closed if this value is missing.

Keep port `8091` private. The public hostname should terminate HTTPS in the reverse proxy and forward only the sales routes to `127.0.0.1:8091`. Set the proxy request body limit for `/v1/sales/webhooks/agentmail` to `256k` or lower.

## Start In Dry Run

Start the public API first:

```bash
systemctl enable --now virtual-org-sales-public-api
systemctl status virtual-org-sales-public-api
```

Start the worker while the kill switch is still on:

```bash
systemctl enable --now virtual-org-sales-worker
systemctl status virtual-org-sales-worker
```

The worker should report that sending is blocked while `SALES_KILL_SWITCH=true`. That is expected.

## Health Checks

Control API health:

```bash
curl http://127.0.0.1:8080/health
```

Sales public API health:

```bash
curl http://127.0.0.1:8091/health
```

Sales agent health:

```bash
set -a
source /opt/virtual-org/.env
set +a
curl -s http://127.0.0.1:8080/v1/sales/health \
  -H "Authorization: Bearer $CONTROL_API_TOKEN"
```

## Live Logs

Press `Ctrl + C` to stop watching logs.

```bash
journalctl -u virtual-org-sales-public-api -f
journalctl -u virtual-org-sales-worker -f
```

## First Live Send

Before live mode:

- confirm AgentMail sender verification
- confirm the webhook is configured in AgentMail
- confirm the unsubscribe URL opens from the public internet
- confirm Slack approvals are working
- review the dry-run summary in the control API

Request first-live approval:

```bash
set -a
source /opt/virtual-org/.env
set +a
curl -X POST http://127.0.0.1:8080/v1/sales/agents/AGENT_ID/request-live-approval \
  -H "Authorization: Bearer $CONTROL_API_TOKEN"
```

After approval, update `/opt/virtual-org/.env`:

```env
SALES_AGENT_ENABLED=true
SALES_SEND_MODE=live
SALES_KILL_SWITCH=false
```

Also set the agent row to live mode through the internal API:

```bash
curl -X POST http://127.0.0.1:8080/v1/sales/agents/AGENT_ID/send-mode \
  -H "Authorization: Bearer $CONTROL_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"send_mode":"live"}'
```

Then restart the worker:

```bash
systemctl restart virtual-org-sales-worker
```

## Apollo Signal Imports

Use Apollo imports only after the dry-run flow works with manual prospects. Start with a tiny batch and a signal threshold:

```bash
curl -X POST http://127.0.0.1:8080/v1/sales/agents/AGENT_ID/import \
  -H "Authorization: Bearer $CONTROL_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "apollo",
    "apollo_search": {
      "person_titles": ["Founder", "CEO", "Head of Growth"],
      "person_locations": ["United Kingdom"],
      "organization_locations": ["United Kingdom"],
      "per_page": 10,
      "min_signal_score": 50,
      "signal_keywords": ["growth", "paid social", "marketing", "ecommerce", "saas"]
    }
  }'
```

The response includes diagnostics:

```json
{
  "returned": 10,
  "imported": 0,
  "skipped_low_signal": 2,
  "missing_email": 8,
  "missing_company": 0,
  "invalid_country": 0
}
```

If `missing_email` is high, Apollo is finding people but not returning unlocked email addresses.

## Emergency Stop

This is the fastest safe stop:

```bash
cd /opt/virtual-org
python3 - <<'PY'
from pathlib import Path
path = Path(".env")
text = path.read_text()
if "SALES_KILL_SWITCH=" in text:
    lines = []
    for line in text.splitlines():
        if line.startswith("SALES_KILL_SWITCH="):
            lines.append("SALES_KILL_SWITCH=true")
        else:
            lines.append(line)
    path.write_text("\n".join(lines) + "\n")
else:
    path.write_text(text.rstrip() + "\nSALES_KILL_SWITCH=true\n")
PY
systemctl restart virtual-org-sales-worker
```

You can also stop the worker completely:

```bash
systemctl stop virtual-org-sales-worker
```

Stopping the worker prevents new sends. Keep the public API running so unsubscribe links and webhooks still work.

## Common Problems

### Worker says sending is blocked

Check:

- `SALES_AGENT_ENABLED`
- `SALES_SEND_MODE`
- `SALES_KILL_SWITCH`
- first-live approval status
- sender verification
- sales health output

### Public unsubscribe page does not open

Check:

- `virtual-org-sales-public-api` is running
- `CONTROL_PUBLIC_BASE_URL` points to the public hostname
- reverse proxy routing sends sales public traffic to port `8091`

### Replies are not creating Slack attention items

Check:

- AgentMail webhook is pointed at `/v1/sales/webhooks/agentmail`
- `AGENTMAIL_WEBHOOK_SECRET` matches AgentMail
- Slack dispatcher is running
- sales public API logs show webhook events arriving
