# Virtual Org Workspace

This workspace is now aligned to the Paperclip-based build only.

The older Tempa-specific story still exists in parts of the codebase because this repo started as a different prototype. Treat that as legacy scaffolding, not as the current product direction.

## Current Rules

- New work should assume a Paperclip-based build.
- Do not add new Tempa-specific prompts, categories, defaults, or repo targets.
- Do not assume a default target repo. Set `ALLOWED_REPOS` explicitly in `.env`.
- If you touch legacy files, prefer removing hidden assumptions instead of extending them.

## What This Repo Still Contains

- A legacy Slack capture and worker loop in `bot.py`, `triage.py`, and `worker.py`
- Research and implementation helpers in `research.py` and `implement.py`
- An older content pipeline experiment in `content_pipeline.py`

These files are still useful as raw material, but they are not the source of truth for strategy.

## Legacy Local Run

If you need to run the current Python harness locally:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env

.venv/bin/python3 scripts/setup_db.py
.venv/bin/python3 bot.py
.venv/bin/python3 worker.py
```

## macOS Background Services

If you want the legacy bot and worker to restart automatically on your Mac:

```bash
chmod +x scripts/install_launchd_services.sh scripts/uninstall_launchd_services.sh scripts/status_launchd_services.sh
./scripts/install_launchd_services.sh
```

Logs go to `.context/launchd-logs/`.

See [CLAUDE.md](CLAUDE.md) for the workspace guide agents should follow.
