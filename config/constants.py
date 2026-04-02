"""Central configuration for Virtual Org."""

import os

# --- Models ---
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_FAST_MODEL = "claude-haiku-4-5-20251001"
TRIAGE_MODEL = CLAUDE_FAST_MODEL  # Fast + cheap for classification
RESEARCH_MODEL = CLAUDE_MODEL     # Needs to reason about code
IMPLEMENT_MODEL = CLAUDE_MODEL    # Needs to plan implementations

# --- Timing ---
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
TRIAGE_INTERVAL_SECONDS = int(os.getenv("TRIAGE_INTERVAL_SECONDS", "300"))
HEARTBEAT_INTERVAL_SECONDS = 30
IMPLEMENT_TIMEOUT_SECONDS = int(os.getenv("IMPLEMENT_TIMEOUT_SECONDS", "300"))
DEFAULT_LEASE_SECONDS = max(180, IMPLEMENT_TIMEOUT_SECONDS + 120)
LEASE_SECONDS = int(os.getenv("LEASE_SECONDS", str(DEFAULT_LEASE_SECONDS)))

# --- Limits ---
MAX_RESEARCH_TOKENS = 4000
MAX_TRIAGE_TOKENS = 2000
MAX_IMPLEMENT_TOKENS = 8000

# --- Categories ---
IDEA_CATEGORIES = [
    "tempa-feature",
    "tempa-bug",
    "business",
    "content",
    "research",
    "random",
]

ACTIONABLE_CATEGORIES = ["tempa-feature", "tempa-bug", "research"]

# --- Task statuses ---
TASK_STATUSES_ACTIVE = ["queued", "claimed", "researching", "implementing"]
TASK_STATUSES_FINAL = ["pr_open", "done", "failed"]

# --- Allowed repos ---
ALLOWED_REPOS = [
    r.strip()
    for r in os.getenv("ALLOWED_REPOS", "maxshepcross/tempa").split(",")
    if r.strip()
]
