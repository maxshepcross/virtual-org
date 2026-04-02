#!/usr/bin/env python3
"""Bootstrap the virtual_org Postgres schema."""

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
-- Ideas: raw captures from Slack
CREATE TABLE IF NOT EXISTS ideas (
    id              BIGSERIAL PRIMARY KEY,
    slack_ts        TEXT UNIQUE,
    slack_thread_ts TEXT,
    slack_channel   TEXT,
    slack_user      TEXT,

    -- Raw input
    raw_text        TEXT NOT NULL,
    raw_image_url   TEXT,
    voice_transcript TEXT,

    -- Triage results (filled by triage agent)
    status          TEXT NOT NULL DEFAULT 'raw',
    category        TEXT,
    title           TEXT,
    structured_body TEXT,
    effort          TEXT,
    impact          TEXT,
    target_repo     TEXT,
    triage_json     JSONB,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    triaged_at      TIMESTAMPTZ,
    archived_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ideas_status ON ideas(status);
CREATE INDEX IF NOT EXISTS idx_ideas_category ON ideas(category);
CREATE INDEX IF NOT EXISTS idx_ideas_created ON ideas(created_at DESC);

-- Tasks: work items created from triaged ideas
CREATE TABLE IF NOT EXISTS tasks (
    id              BIGSERIAL PRIMARY KEY,
    idea_id         BIGINT REFERENCES ideas(id),

    -- Task definition
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    category        TEXT NOT NULL,
    target_repo     TEXT,

    -- Queue state
    status          TEXT NOT NULL DEFAULT 'queued',
    worker_id       TEXT,
    lease_token     UUID,
    lease_expires_at TIMESTAMPTZ,
    last_heartbeat_at TIMESTAMPTZ,

    -- Agent outputs
    research_json   JSONB,
    implementation_json JSONB,
    pr_url          TEXT,
    pr_number       INTEGER,
    pr_status       TEXT,
    branch_name     TEXT,
    error_message   TEXT,

    -- Audit
    events          JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_idea ON tasks(idea_id);

-- Unique: only one active task per idea
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_active_idea
    ON tasks(idea_id)
    WHERE status IN ('queued', 'claimed', 'researching', 'implementing');

-- Content interviews: weekly conversations to extract stories and opinions
CREATE TABLE IF NOT EXISTS content_interviews (
    id              BIGSERIAL PRIMARY KEY,
    slack_user      TEXT NOT NULL,
    slack_channel   TEXT NOT NULL,
    slack_thread_ts TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
    questions       JSONB NOT NULL DEFAULT '[]'::JSONB,
    question_index  INTEGER NOT NULL DEFAULT 0,
    trends_json     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_interviews_user_status
    ON content_interviews(slack_user, status);

-- Content drafts: generated posts for X and LinkedIn
CREATE TABLE IF NOT EXISTS content_drafts (
    id              BIGSERIAL PRIMARY KEY,
    interview_id    BIGINT REFERENCES content_interviews(id),
    platform        TEXT NOT NULL,
    draft_text      TEXT NOT NULL,
    hook            TEXT,
    topic           TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    slack_channel   TEXT,
    slack_ts        TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at     TIMESTAMPTZ,
    posted_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_drafts_interview ON content_drafts(interview_id);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON content_drafts(status);
CREATE INDEX IF NOT EXISTS idx_drafts_slack_ts ON content_drafts(slack_ts);
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
