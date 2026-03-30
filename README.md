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

## How It Works

1. **You DM the Slack bot** with a raw idea (text, voice memo, photo)
2. **Triage agent** classifies it: category, effort, impact, approach
3. **Research agent** explores the codebase, checks feasibility
4. **Implementation agent** makes changes via Claude Code, opens a PR
5. **You review the PR** when you sit down

See [CLAUDE.md](CLAUDE.md) for full documentation.
