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
