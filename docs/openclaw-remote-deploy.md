# Remote OpenClaw Deployment

This repo is now set up for a remote control-plane plus remote OpenClaw runtime.

## Target shape

- `VM 1`: OpenClaw gateway and worker runtime
- `VM 2`: Python control API and Postgres
- private network between them, ideally Tailscale

For V1 you can collapse both onto one remote VM.

## Python control API

1. Copy `.env.example` to `.env`
2. Set:
   - `DATABASE_URL`
   - `CONTROL_API_TOKEN`
   - `SLACK_APPROVER_IDS`
3. Run the schema:
   - `.venv/bin/python3 scripts/setup_db.py`
4. Run the API:
   - `.venv/bin/python3 scripts/run_api.py`

Default bind:
- host: `127.0.0.1`
- port: `8080`

Override with:
- `CONTROL_API_HOST`
- `CONTROL_API_PORT`

## OpenClaw gateway

1. Install OpenClaw on the remote runtime box.
2. Copy the plugin from:
   - `openclaw/plugins/studio-control/`
3. Load the plugin using:
   - `openclaw/gateway.example.json`
4. Point the plugin at the control API base URL and token.
5. Configure Slack allowlists on the gateway.

## Chief workspace

Use:
- `openclaw/workspaces/studio-chief/AGENTS.md`
- `openclaw/workspaces/studio-chief/HEARTBEAT.md`

These files are the starting behavior for the chief agent.

## Current gap

What is built here:
- control API
- policy engine
- approval and attention state
- OpenClaw bridge plugin source
- chief workspace templates

What still depends on real remote infrastructure:
- live Slack token and channel wiring
- real OpenClaw gateway install
- plugin compile/install on the gateway host
- production process manager and TLS
