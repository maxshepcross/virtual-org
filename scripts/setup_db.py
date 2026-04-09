#!/usr/bin/env python3
"""Bootstrap the AI Venture Studio task schema."""

import os
import sys
from pathlib import Path

import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.env import load_project_env

load_project_env()

SCHEMA_SQL = """
-- Tasks: queued work items for the studio control plane
CREATE TABLE IF NOT EXISTS tasks (
    id              BIGSERIAL PRIMARY KEY,
    idea_id         BIGINT,

    -- Task definition
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    category        TEXT NOT NULL,
    target_repo     TEXT,
    venture         TEXT,
    requested_by    TEXT,

    -- Queue state
    status          TEXT NOT NULL DEFAULT 'queued',
    worker_id       TEXT,
    lease_token     UUID,
    lease_expires_at TIMESTAMPTZ,
    last_heartbeat_at TIMESTAMPTZ,

    -- Agent outputs
    research_json   JSONB,
    execution_stories_json JSONB,
    implementation_json JSONB,
    progress_notes_json JSONB,
    verification_json JSONB,
    current_story_id TEXT,
    pr_url          TEXT,
    pr_number       INTEGER,
    pr_status       TEXT,
    branch_name     TEXT,
    slack_channel_id TEXT,
    slack_thread_ts TEXT,
    approval_state  TEXT,
    latest_attention_severity TEXT,
    error_message   TEXT,

    -- Audit
    events          JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_idea ON tasks(idea_id);
CREATE INDEX IF NOT EXISTS idx_tasks_slack_channel ON tasks(slack_channel_id);

-- Unique: only one active task per idea
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_active_idea
    ON tasks(idea_id)
    WHERE status IN ('queued', 'claimed', 'triaged', 'researching', 'awaiting_approval', 'implementing', 'reviewing', 'blocked');

CREATE TABLE IF NOT EXISTS agent_runs (
    id              BIGSERIAL PRIMARY KEY,
    task_id         BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
    run_key         TEXT NOT NULL,
    parent_run_id   BIGINT REFERENCES agent_runs(id) ON DELETE SET NULL,
    story_id        TEXT,
    run_kind        TEXT NOT NULL DEFAULT 'interactive',
    trigger_source  TEXT NOT NULL DEFAULT 'manual',
    triggered_by    TEXT,
    approved_by     TEXT,
    completed_by    TEXT,
    agent_class     TEXT NOT NULL,
    agent_role      TEXT NOT NULL,
    repo_name       TEXT,
    branch_name     TEXT,
    pr_url          TEXT,
    slack_channel_id TEXT,
    slack_thread_ts TEXT,
    openclaw_session_id TEXT,
    status          TEXT NOT NULL DEFAULT 'running',
    artifact_summary_json JSONB NOT NULL DEFAULT '[]'::JSONB,
    context_json    JSONB,
    tool_bundle_json JSONB,
    resume_context_json JSONB,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    last_heartbeat_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_task_id ON agent_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_runs_run_key ON agent_runs(run_key);
CREATE INDEX IF NOT EXISTS idx_agent_runs_parent_run_id ON agent_runs(parent_run_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_trigger_source ON agent_runs(trigger_source);

CREATE TABLE IF NOT EXISTS signals (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,
    kind            TEXT NOT NULL,
    task_id         BIGINT REFERENCES tasks(id) ON DELETE SET NULL,
    agent_run_id    BIGINT REFERENCES agent_runs(id) ON DELETE SET NULL,
    venture         TEXT,
    severity        TEXT NOT NULL,
    summary         TEXT NOT NULL,
    details_json    JSONB,
    dedupe_key      TEXT NOT NULL,
    bucket          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_task_id ON signals(task_id);
CREATE INDEX IF NOT EXISTS idx_signals_agent_run_id ON signals(agent_run_id);
CREATE INDEX IF NOT EXISTS idx_signals_bucket ON signals(bucket);
CREATE INDEX IF NOT EXISTS idx_signals_dedupe ON signals(dedupe_key);

CREATE TABLE IF NOT EXISTS attention_items (
    id              BIGSERIAL PRIMARY KEY,
    signal_id       BIGINT REFERENCES signals(id) ON DELETE SET NULL,
    task_id         BIGINT REFERENCES tasks(id) ON DELETE SET NULL,
    agent_run_id    BIGINT REFERENCES agent_runs(id) ON DELETE SET NULL,
    venture         TEXT,
    bucket          TEXT NOT NULL,
    severity        TEXT NOT NULL,
    headline        TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    slack_channel_id TEXT,
    slack_thread_ts TEXT,
    status          TEXT NOT NULL DEFAULT 'open',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_attention_items_task_id ON attention_items(task_id);
CREATE INDEX IF NOT EXISTS idx_attention_items_agent_run_id ON attention_items(agent_run_id);
CREATE INDEX IF NOT EXISTS idx_attention_items_status ON attention_items(status);
CREATE INDEX IF NOT EXISTS idx_attention_items_bucket ON attention_items(bucket);

CREATE TABLE IF NOT EXISTS approval_requests (
    id              BIGSERIAL PRIMARY KEY,
    task_id         BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
    agent_run_id    BIGINT REFERENCES agent_runs(id) ON DELETE SET NULL,
    action_type     TEXT NOT NULL,
    target_summary  TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    requested_slack_channel_id TEXT,
    requested_slack_thread_ts TEXT,
    approved_by_slack_user_id TEXT,
    resolution_note TEXT,
    external_event_id TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_approval_requests_external_event_id
    ON approval_requests(external_event_id)
    WHERE external_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_approval_requests_status ON approval_requests(status);

CREATE TABLE IF NOT EXISTS policy_decisions (
    id              BIGSERIAL PRIMARY KEY,
    agent_run_id    BIGINT REFERENCES agent_runs(id) ON DELETE SET NULL,
    task_id         BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
    story_id        TEXT,
    tool_name       TEXT,
    action_type     TEXT NOT NULL,
    target_type     TEXT,
    target_host     TEXT,
    target_repo     TEXT,
    decision        TEXT NOT NULL,
    policy_name     TEXT NOT NULL,
    reason          TEXT NOT NULL,
    approval_request_id BIGINT REFERENCES approval_requests(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_policy_decisions_task_id ON policy_decisions(task_id);
CREATE INDEX IF NOT EXISTS idx_policy_decisions_decision ON policy_decisions(decision);

CREATE TABLE IF NOT EXISTS network_requests (
    id              BIGSERIAL PRIMARY KEY,
    agent_run_id    BIGINT REFERENCES agent_runs(id) ON DELETE SET NULL,
    task_id         BIGINT REFERENCES tasks(id) ON DELETE SET NULL,
    target_host     TEXT NOT NULL,
    method          TEXT,
    path_hint       TEXT,
    decision        TEXT NOT NULL,
    bytes_sent      BIGINT,
    bytes_received  BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_network_requests_task_id ON network_requests(task_id);

CREATE TABLE IF NOT EXISTS briefings (
    id              BIGSERIAL PRIMARY KEY,
    scope           TEXT NOT NULL,
    headline        TEXT NOT NULL,
    items_json      JSONB NOT NULL DEFAULT '[]'::JSONB,
    delivered_to    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS slack_routes (
    id              BIGSERIAL PRIMARY KEY,
    task_id         BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
    slack_channel_id TEXT NOT NULL,
    slack_thread_ts TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_slack_routes_task_id ON slack_routes(task_id);

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS execution_stories_json JSONB;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS progress_notes_json JSONB;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS verification_json JSONB;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS current_story_id TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS venture TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS requested_by TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS slack_channel_id TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS slack_thread_ts TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS approval_state TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS latest_attention_severity TEXT;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS run_key TEXT;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS parent_run_id BIGINT REFERENCES agent_runs(id) ON DELETE SET NULL;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS run_kind TEXT NOT NULL DEFAULT 'interactive';
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS trigger_source TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS triggered_by TEXT;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS approved_by TEXT;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS completed_by TEXT;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS repo_name TEXT;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS branch_name TEXT;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS pr_url TEXT;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS slack_channel_id TEXT;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS slack_thread_ts TEXT;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS artifact_summary_json JSONB NOT NULL DEFAULT '[]'::JSONB;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS context_json JSONB;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS tool_bundle_json JSONB;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS agent_run_id BIGINT REFERENCES agent_runs(id) ON DELETE SET NULL;
ALTER TABLE attention_items ADD COLUMN IF NOT EXISTS agent_run_id BIGINT REFERENCES agent_runs(id) ON DELETE SET NULL;
ALTER TABLE attention_items ADD COLUMN IF NOT EXISTS slack_message_ts TEXT;
ALTER TABLE attention_items ADD COLUMN IF NOT EXISTS slack_posted_at TIMESTAMPTZ;
ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS slack_message_ts TEXT;
ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS slack_posted_at TIMESTAMPTZ;
UPDATE agent_runs SET run_key = id::text WHERE run_key IS NULL OR BTRIM(run_key) = '';
ALTER TABLE agent_runs ALTER COLUMN run_key SET NOT NULL;
"""


def main():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set in .env")
        sys.exit(1)

    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        print("Schema created successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
