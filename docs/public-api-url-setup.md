# Public API URL Setup

Slack cannot reach `127.0.0.1` or `localhost`.
Those are private addresses that only work from inside the server.

To connect Slack to the control API, create a public `https` URL that forwards to the local API on `127.0.0.1:8080`.

Recommended production shape:

```text
Slack -> https://control.yourdomain.com -> Caddy -> 127.0.0.1:8080 -> FastAPI control API
```

Caddy is a small web server. Here it acts like a front door: Slack knocks on the public HTTPS door, and Caddy passes the request to the private local API.

## Step 1: choose a domain

Use a subdomain like:

```text
control.yourdomain.com
```

Point that domain's `A` record to the public IP address of the server running `virtual-org-control-api`.

If you do not have a domain ready, use a temporary tunnel for testing instead, but do not treat that as the long-term setup.

For this deployment, use:

```text
openclaw.tempa.agency
```

Do not repoint `tempa.agency` itself. The root domain is the public Tempa site. A subdomain lets Slack reach OpenClaw without risking the main website.

## Step 2: install Caddy on the server

On Ubuntu or Debian, follow Caddy's official install instructions.
After Caddy is installed, it should run as a system service.

## Step 3: add the Caddy config

Use the template in:

```text
deploy/caddy/Caddyfile.example
```

Copy it into Caddy's config file and replace the domain:

```caddyfile
control.yourdomain.com {
	reverse_proxy 127.0.0.1:8080
}
```

Typical destination on the server:

```text
/etc/caddy/Caddyfile
```

## Step 4: reload Caddy

Run:

```bash
systemctl reload caddy
```

If Caddy is not running yet:

```bash
systemctl enable --now caddy
```

## Step 5: test the public URL

From your laptop, open:

```text
https://control.yourdomain.com/health
```

Healthy response:

```json
{"status":"ok"}
```

If that works, your API base URL is:

```text
https://control.yourdomain.com
```

Use that value in the Slack manifest:

```text
https://control.yourdomain.com/slack/events
https://control.yourdomain.com/slack/interactivity
```

## Common failure points

### The browser cannot reach the URL

Check:

- the domain points at the server's public IP address
- ports `80` and `443` are open on the server firewall
- Caddy is running

### The URL loads but `/health` fails

Check:

- `virtual-org-control-api` is running
- the API is still listening on `127.0.0.1:8080`
- Caddy is reverse-proxying to `127.0.0.1:8080`

### Slack verification fails

Check:

- the Slack manifest uses `https`, not `http`
- the URL path is exactly `/slack/events`
- `SLACK_SIGNING_SECRET` is set on the server
- the API was restarted after `.env` changed
