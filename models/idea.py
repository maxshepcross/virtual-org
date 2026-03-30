"""Idea data model — raw captures from Slack, triaged by agents."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras
from pydantic import BaseModel, Field


class Idea(BaseModel):
    id: int | None = None
    slack_ts: str | None = None
    slack_thread_ts: str | None = None
    slack_channel: str | None = None
    slack_user: str | None = None

    raw_text: str
    raw_image_url: str | None = None
    voice_transcript: str | None = None

    status: str = "raw"  # raw → triaged → tasked → archived
    category: str | None = None
    title: str | None = None
    structured_body: str | None = None
    effort: str | None = None
    impact: str | None = None
    target_repo: str | None = None
    triage_json: dict[str, Any] | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    triaged_at: datetime | None = None
    archived_at: datetime | None = None


def _conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def _row_to_idea(row: dict) -> Idea:
    if row.get("triage_json") and isinstance(row["triage_json"], str):
        row["triage_json"] = json.loads(row["triage_json"])
    return Idea(**row)


def create_idea(
    raw_text: str,
    slack_ts: str | None = None,
    slack_thread_ts: str | None = None,
    slack_channel: str | None = None,
    slack_user: str | None = None,
    raw_image_url: str | None = None,
    voice_transcript: str | None = None,
) -> Idea:
    """Insert a new raw idea. Returns the created Idea."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO ideas (raw_text, slack_ts, slack_thread_ts, slack_channel, slack_user,
                                   raw_image_url, voice_transcript)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (raw_text, slack_ts, slack_thread_ts, slack_channel, slack_user,
                 raw_image_url, voice_transcript),
            )
            conn.commit()
            return _row_to_idea(cur.fetchone())
    finally:
        conn.close()


def get_raw_ideas() -> list[Idea]:
    """Fetch all ideas with status='raw' for triage."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM ideas WHERE status = 'raw' ORDER BY created_at ASC"
            )
            return [_row_to_idea(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_recent_ideas(limit: int = 20) -> list[Idea]:
    """Fetch recent ideas for context (duplicate detection, clustering)."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM ideas WHERE status != 'raw' ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            return [_row_to_idea(row) for row in cur.fetchall()]
    finally:
        conn.close()


def update_idea_triage(
    idea_id: int,
    category: str,
    title: str,
    structured_body: str,
    effort: str,
    impact: str,
    target_repo: str | None,
    triage_json: dict[str, Any],
) -> Idea:
    """Update an idea with triage results."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE ideas
                SET status = 'triaged', category = %s, title = %s,
                    structured_body = %s, effort = %s, impact = %s,
                    target_repo = %s, triage_json = %s,
                    triaged_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (category, title, structured_body, effort, impact,
                 target_repo, json.dumps(triage_json), idea_id),
            )
            conn.commit()
            return _row_to_idea(cur.fetchone())
    finally:
        conn.close()


def mark_idea_tasked(idea_id: int) -> None:
    """Mark an idea as having a task created for it."""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ideas SET status = 'tasked' WHERE id = %s", (idea_id,)
            )
            conn.commit()
    finally:
        conn.close()


def archive_idea(idea_id: int) -> None:
    """Archive an idea (user decided not to pursue)."""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ideas SET status = 'archived', archived_at = NOW() WHERE id = %s",
                (idea_id,),
            )
            conn.commit()
    finally:
        conn.close()
