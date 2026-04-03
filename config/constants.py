"""Central configuration for the workspace automation harness."""

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
    "paperclip-feature",
    "paperclip-bug",
    "business",
    "content",
    "research",
    "random",
]
LEGACY_CODE_CATEGORIES = ["tempa-feature", "tempa-bug"]
CODE_TASK_CATEGORIES = ["paperclip-feature", "paperclip-bug", *LEGACY_CODE_CATEGORIES]
ACTIONABLE_CATEGORIES = [*CODE_TASK_CATEGORIES, "research"]

# --- Task statuses ---
TASK_STATUSES_ACTIVE = ["queued", "claimed", "researching", "implementing"]
TASK_STATUSES_FINAL = ["pr_open", "done", "failed"]

# --- Content Pipeline ---
CONTENT_MODEL = CLAUDE_MODEL             # Sonnet for quality drafts
CONTENT_OWNER_SLACK_USER = os.getenv("CONTENT_OWNER_SLACK_USER", "")
CONTENT_INTERVIEW_DAY = os.getenv("CONTENT_INTERVIEW_DAY", "monday").lower()
CONTENT_INTERVIEW_HOUR = int(os.getenv("CONTENT_INTERVIEW_HOUR", "10"))
CONTENT_CHECK_INTERVAL_SECONDS = 60
INTERVIEW_QUESTION_COUNT = 5
INTERVIEW_STALE_HOURS = 48  # Auto-cancel after this many hours
MAX_CONTENT_TOKENS = 4000
CONTENT_TOPICS = ["entrepreneurship", "AI", "building in public", "solo founding"]

# --- Allowed repos ---
ALLOWED_REPOS = [
    r.strip()
    for r in os.getenv("ALLOWED_REPOS", "").split(",")
    if r.strip()
]
