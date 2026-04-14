# Quick Tunnel Slack Test

Use this when you want to test the Slack agent before buying or configuring a real domain.

This creates a temporary public URL like:

```text
https://random-words.trycloudflare.com
```

It forwards to the control API on:

```text
http://localhost:8080
```

Important: this URL is temporary. If the tunnel process stops, the URL stops working and you will need to update the Slack app again.

## Step 1: confirm the API is running

On the DigitalOcean droplet:

```bash
curl http://127.0.0.1:8080/health
```

Healthy response:

```json
{"status":"ok"}
```

## Step 2: install cloudflared

On the DigitalOcean droplet:

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb
sudo dpkg -i /tmp/cloudflared.deb
cloudflared --version
```

## Step 3: start the temporary tunnel

Run:

```bash
cloudflared tunnel --url http://localhost:8080
```

Keep this terminal open.

Cloudflare will print a public URL that looks like:

```text
https://random-words.trycloudflare.com
```

That is the temporary API base URL.

## Step 4: test the temporary URL

Open:

```text
https://random-words.trycloudflare.com/health
```

Healthy response:

```json
{"status":"ok"}
```

## Step 5: use it in Slack

In the Slack app manifest, replace `https://YOUR_CONTROL_API_HOST` with the temporary URL.

Example:

```text
https://random-words.trycloudflare.com/slack/events
https://random-words.trycloudflare.com/slack/interactivity
```

Then save and reinstall the Slack app.

## Step 6: remember the limitation

If the tunnel stops or the terminal closes:

- Slack events stop working
- button clicks stop working
- you need to start a new tunnel and paste the new URL into Slack

Use this only for testing. For production, use `docs/public-api-url-setup.md`.
