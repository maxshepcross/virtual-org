# Virtual Org — Project Guide

## What Is This?

Virtual Org is a personal AI operating system for a solo founder. You DM a Slack bot with raw ideas (text, voice, photos), and AI agents triage them, research feasibility, implement code changes, and open PRs — all without you sitting at a computer.

The goal: capture ideas when your mind is open, review completed work when you sit down.

---

## How to Run It

```bash
# First time setup
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # Fill in your values

# Bootstrap the database
.venv/bin/python3 scripts/setup_db.py

# Start the Slack bot (captures ideas + runs triage loop)
.venv/bin/python3 bot.py

# Start the worker (claims tasks, researches, implements, opens PRs)
.venv/bin/python3 worker.py

# Run triage manually
.venv/bin/python3 triage.py
```

**Required keys** (in `.env`):
- `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN` — Slack Socket Mode bot
- `ANTHROPIC_API_KEY` — Claude for triage + research
- `DATABASE_URL` — PostgreSQL connection
- `GITHUB_TOKEN` — For pushing branches and opening PRs

---

## Architecture

```
Slack DM → bot.py → ideas table → triage.py → tasks table → worker.py
                                                                ├─ research.py
                                                                └─ implement.py → PR

Weekly schedule → bot.py → content_pipeline.py
                              ├─ Interview (5 adaptive questions via Slack)
                              ├─ Trend research (Claude + web search)
                              └─ Draft posts (X + LinkedIn) → Slack for review
```

### Capture Layer (`bot.py`)
- Slack Bolt app using Socket Mode (no public URL needed)
- Captures any DM as a raw idea (unless the user is in an active interview — those messages go to the content pipeline)
- Runs triage loop + content interview scheduling in background threads
- Handles emoji reactions on content drafts (approve/reject)

### Triage Engine (`triage.py`)
- Classifies raw ideas: tempa-feature, tempa-bug, business, content, research, random
- Estimates effort (small/medium/large) and impact (low/medium/high)
- Creates tasks for actionable ideas
- Notifies via Slack thread reply

### Worker (`worker.py`)
- Polls task queue, claims with FOR UPDATE SKIP LOCKED
- Lease-based heartbeating (mirrors Tempa's job_queue pattern)
- Runs research → implementation → PR pipeline

### Research Agent (`research.py`)
- Clones/pulls target repo
- Searches codebase for relevant files
- Produces feasibility assessment + implementation plan via Claude

### Implementation Agent (`implement.py`)
- Creates feature branch
- Runs Claude Code as subprocess to make changes
- Commits, pushes, opens PR via gh CLI

### Content Pipeline (`content_pipeline.py`)
- Weekly interview: 5 adaptive questions via Slack DM (each question builds on the previous answer)
- Trend research: uses Claude + web search to find what's trending in entrepreneurship/AI on X and LinkedIn
- Draft generation: creates 2 X posts + 2 LinkedIn posts combining interview answers with trends
- Review: sends drafts to Slack for emoji-based approval

---

## Key Files

| File | What It Does |
|------|-------------|
| `bot.py` | Slack bot (capture) + triage loop |
| `worker.py` | Task worker (claim → research → implement → PR) |
| `triage.py` | Classifies raw ideas into structured tasks |
| `research.py` | Investigates feasibility, produces implementation plans |
| `implement.py` | Runs Claude Code to make changes, opens PRs |
| `models/idea.py` | Idea data model + Postgres CRUD |
| `models/task.py` | Task queue with atomic claiming + heartbeating |
| `services/slack_notify.py` | Slack notification helpers |
| `services/github_ops.py` | Branch creation, commit, push, PR opening |
| `scripts/setup_db.py` | Database schema bootstrap |
| `config/constants.py` | Models, timing, categories |
| `content_pipeline.py` | Weekly content interview + trend research + draft generation |
| `models/content.py` | Interview + ContentDraft models + Postgres CRUD |
| `prompts/triage.md` | Triage classification prompt |
| `prompts/research.md` | Research/feasibility prompt |
| `prompts/interview.md` | Adaptive interview question generation prompt |
| `prompts/content_draft.md` | X + LinkedIn post drafting prompt |

---

## Database

Four Postgres tables:

- **ideas** — Raw captures from Slack. Status: raw → triaged → tasked → archived
- **tasks** — Work items for agents. Status: queued → claimed → researching → implementing → pr_open → done → failed
- **content_interviews** — Weekly interview sessions. Status: active → completed → cancelled
- **content_drafts** — Generated social media posts. Status: pending → approved → rejected → posted

Task claiming uses `FOR UPDATE SKIP LOCKED` with lease tokens (same pattern as Tempa's job queue).

---

## Slack Bot Setup

1. Create a Slack app at https://api.slack.com/apps
2. Enable **Socket Mode** (no public URL needed)
3. Add bot scopes: `chat:write`, `im:history`, `im:read`, `im:write`, `files:read`, `reactions:read`
4. Subscribe to events: `message.im`, `reaction_added`
5. Install to workspace, copy tokens to `.env`

---

## Important Things to Know

- **Socket Mode means no public URL.** The bot connects outbound to Slack. Works from your laptop or Railway.
- **Worker runs one task at a time.** Sequential by design — safer for v1. Scale by running multiple workers later.
- **Implementation uses Claude Code subprocess.** The agent spawns `claude --print --dangerously-skip-permissions` with a carefully scoped prompt.
- **Repos are cloned to `.repos/`.** The research and implementation agents work on local clones.
- **All notifications go to the original Slack thread.** You can see the full lifecycle by scrolling up in the DM.
- **ALLOWED_REPOS controls what the agent can modify.** Only repos listed in the env var are valid targets.
- **Content pipeline is opt-in.** Set `CONTENT_OWNER_SLACK_USER` in `.env` to enable weekly interviews. Without it, the content loop does nothing.
- **Content interviews run on a schedule.** Default: Monday at 10am UTC. Change with `CONTENT_INTERVIEW_DAY` and `CONTENT_INTERVIEW_HOUR`.
- **Stale interviews auto-cancel after 48 hours.** If you don't finish the questions, it resets for next week.
- **Draft approval uses emoji reactions.** React with :white_check_mark: to approve, :x: to reject. Approved drafts are saved for posting (v1 is copy-paste, v2 will auto-post).
