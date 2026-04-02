# Virtual Org

Personal AI operating system. Capture ideas on the go via Slack DM, agents triage, research, and implement them — opening PRs while you're still on your walk.

## Quick Start

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # Fill in your keys

.venv/bin/python3 scripts/setup_db.py   # Bootstrap Postgres
.venv/bin/python3 bot.py                # Slack bot + triage
.venv/bin/python3 worker.py             # Task worker (separate terminal)
```

## Keep It Running On Your Mac

If you want Virtual Org to start automatically when you log in and restart if it crashes, use the built-in macOS service manager:

```bash
chmod +x scripts/install_launchd_services.sh scripts/uninstall_launchd_services.sh scripts/status_launchd_services.sh
./scripts/install_launchd_services.sh
```

This keeps the bot and worker running in the background on your Mac. Logs go to `.context/launchd-logs/`.

Check status:

```bash
./scripts/status_launchd_services.sh
```

Remove the background services:

```bash
./scripts/uninstall_launchd_services.sh
```

Important: this is "always on" only while your Mac is awake and logged in. If you want true 24/7 uptime, move the bot and worker to a cloud host.

## How It Works

1. **You DM the Slack bot** with a raw idea (text, voice memo, photo)
2. **Triage agent** classifies it: category, effort, impact, approach
3. **Research agent** explores the codebase, checks feasibility
4. **Implementation agent** makes changes via Claude Code, opens a PR
5. **You review the PR** when you sit down

See [CLAUDE.md](CLAUDE.md) for full documentation.
