# Slack Agent Setup

This is the shortest path to getting the new Slack agent live.

## What this setup does

Slack becomes the chat and approval surface.
The control plane and OpenClaw still keep the real logic, safety rules, and state.

## Before you start

You need:

- a public `https` URL that reaches this repo's API server
- a Slack workspace where you can install a custom app
- the bot token and signing secret stored in this repo's `.env`

If you do not have the public `https` URL yet, create it first with:

- `docs/public-api-url-setup.md`

For a temporary test without buying a domain, use:

- `docs/quick-tunnel-slack-test.md`

The two new HTTP endpoints are:

- `POST /slack/events`
- `POST /slack/interactivity`

## Step 1: put the secrets in `.env`

Add these values on the server:

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_APPROVER_IDS=U12345,U67890
```

If you want only named people to approve risky actions, keep `SLACK_APPROVER_IDS` specific.
Do not use `*` unless you explicitly want any reachable Slack user to approve.

## Step 2: create or update the Slack app

Use the manifest in:

- `deploy/slack/virtual-org-app-manifest.yaml`

Replace `https://YOUR_CONTROL_API_HOST` with the real public API base URL before pasting it into Slack.

The manifest already includes the scopes and events this code expects:

- scopes: `assistant:write`, `app_mentions:read`, `chat:write`, `im:history`
- events: `assistant_thread_started`, `assistant_thread_context_changed`, `message.im`, `app_mention`
- interactivity endpoint for approval buttons

### Click path in Slack

This is the founder-friendly path through Slack's developer UI:

1. Go to `api.slack.com/apps`
2. Click `Create New App`
3. Choose `From an app manifest`
4. Pick the target workspace
5. Paste the contents of `deploy/slack/virtual-org-app-manifest.yaml`
6. Replace `https://YOUR_CONTROL_API_HOST` with the real public API base URL before saving
7. Create the app

After the app exists, check these pages in the left sidebar:

- `Agents & AI Apps`
  Make sure the feature is enabled. Per Slack's docs, this is what gives you the top-bar entry point, split pane, suggested prompts, and thread titles.
- `Event Subscriptions`
  Confirm the request URL ends in `/slack/events` and Slack shows it as verified.
- `Interactivity & Shortcuts`
  Confirm interactivity is enabled and the request URL ends in `/slack/interactivity`.
- `OAuth & Permissions`
  Confirm the bot scopes include `assistant:write`, `app_mentions:read`, `chat:write`, and `im:history`.

## Step 3: install the app

Install or reinstall the app into the target Slack workspace after changing scopes.

Slack only grants new permissions after reinstall.

In Slack's developer UI this is usually the `Install App` page or the `OAuth & Permissions` page with an `Install to Workspace` or `Reinstall to Workspace` button.

## Step 4: restart the API service

After changing `.env`, restart the API:

```bash
systemctl restart virtual-org-control-api
```

## Step 5: smoke test the chat flow

In Slack, open the app and try:

- `what is blocked`
- `show approvals`
- `daily briefing`
- `run one worker pass`

Expected result:

- the app replies in Slack
- the worker pass message comes back from the control plane

## Step 6: smoke test approvals

Create a test approval request, then click the Slack buttons.

Expected result:

- the approval message updates in Slack
- the task leaves `awaiting_approval`
- the approval record is updated in the database

## Common failure points

### Slack says the request URL failed verification

Usually one of these is wrong:

- the URL is not public `https`
- the API server is not running
- `SLACK_SIGNING_SECRET` is missing or wrong

Slack's official docs say agent apps need the `Agents & AI Apps` feature enabled plus subscriptions to `assistant_thread_started`, `assistant_thread_context_changed`, and `message.im`. If the split pane never appears, check that page first.

### The app is silent in Slack

Check:

- the app was reinstalled after scope changes
- the event subscription URL points to `/slack/events`
- the bot token is current

### Buttons show but clicking does nothing

Check:

- interactivity is enabled in Slack
- the interactivity URL points to `/slack/interactivity`
- the API logs show the incoming request

## Recommended first live workflow

Do not start by teaching it everything.

Start with one repeated founder loop:

1. Ask what is blocked.
2. Review the pending approvals.
3. Approve or deny inside Slack.
4. Trigger one safe worker pass.

If that loop feels materially better than the old notification-only setup, keep expanding from there.
