"""Content pipeline models — interviews, trends, and post drafts.

Weekly flow: interview → trend research → draft posts → review via Slack.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class Interview(BaseModel):
    id: int | None = None
    slack_user: str
    slack_channel: str
    slack_thread_ts: str | None = None
    status: str = "active"  # active → completed → cancelled
    questions: list[dict[str, Any]] = Field(default_factory=list)
    question_index: int = 0
    trends_json: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


class ContentDraft(BaseModel):
    id: int | None = None
    interview_id: int | None = None
    platform: str  # "x" or "linkedin"
    draft_text: str
    hook: str | None = None
    topic: str | None = None
    status: str = "pending"  # pending → approved → rejected → posted
    slack_channel: str | None = None
    slack_ts: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_at: datetime | None = None
    posted_at: datetime | None = None


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def _row_to_interview(row: dict) -> Interview:
    for field in ("questions", "trends_json"):
        if row.get(field) and isinstance(row[field], str):
            row[field] = json.loads(row[field])
    return Interview(**row)


def _row_to_draft(row: dict) -> ContentDraft:
    return ContentDraft(**row)


# ---------------------------------------------------------------------------
# Interview CRUD
# ---------------------------------------------------------------------------

def create_interview(slack_user: str, slack_channel: str, slack_thread_ts: str) -> Interview:
    """Start a new weekly interview."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO content_interviews (slack_user, slack_channel, slack_thread_ts, questions)
                VALUES (%s, %s, %s, '[]'::jsonb)
                RETURNING *
                """,
                (slack_user, slack_channel, slack_thread_ts),
            )
            conn.commit()
            return _row_to_interview(cur.fetchone())
    finally:
        conn.close()


def get_active_interview(slack_user: str) -> Interview | None:
    """Get the currently active interview for a user (if any)."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM content_interviews
                WHERE slack_user = %s AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (slack_user,),
            )
            row = cur.fetchone()
            return _row_to_interview(row) if row else None
    finally:
        conn.close()


def get_last_completed_interview(slack_user: str) -> Interview | None:
    """Get the most recent completed interview for scheduling."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM content_interviews
                WHERE slack_user = %s AND status = 'completed'
                ORDER BY completed_at DESC
                LIMIT 1
                """,
                (slack_user,),
            )
            row = cur.fetchone()
            return _row_to_interview(row) if row else None
    finally:
        conn.close()


def add_question_to_interview(interview_id: int, question: str) -> Interview:
    """Add a question that was asked (answer will be filled later)."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            new_q = json.dumps({
                "question": question,
                "answer": None,
                "asked_at": datetime.now(timezone.utc).isoformat(),
                "answered_at": None,
            })
            cur.execute(
                """
                UPDATE content_interviews
                SET questions = questions || %s::jsonb,
                    question_index = question_index + 1
                WHERE id = %s
                RETURNING *
                """,
                (new_q, interview_id),
            )
            conn.commit()
            return _row_to_interview(cur.fetchone())
    finally:
        conn.close()


def record_answer(interview_id: int, question_index: int, answer: str) -> Interview:
    """Record the user's answer to the current question."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE content_interviews
                SET questions = jsonb_set(
                    jsonb_set(
                        questions,
                        ARRAY[%s::text, 'answer'],
                        to_jsonb(%s::text)
                    ),
                    ARRAY[%s::text, 'answered_at'],
                    to_jsonb(%s::text)
                )
                WHERE id = %s
                RETURNING *
                """,
                (
                    str(question_index), answer,
                    str(question_index), datetime.now(timezone.utc).isoformat(),
                    interview_id,
                ),
            )
            conn.commit()
            return _row_to_interview(cur.fetchone())
    finally:
        conn.close()


def complete_interview(interview_id: int, trends_json: dict | None = None) -> Interview:
    """Mark an interview as completed."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE content_interviews
                SET status = 'completed',
                    completed_at = NOW(),
                    trends_json = %s
                WHERE id = %s
                RETURNING *
                """,
                (json.dumps(trends_json) if trends_json else None, interview_id),
            )
            conn.commit()
            return _row_to_interview(cur.fetchone())
    finally:
        conn.close()


def cancel_interview(interview_id: int) -> None:
    """Cancel an active interview."""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE content_interviews SET status = 'cancelled' WHERE id = %s",
                (interview_id,),
            )
            conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Content Draft CRUD
# ---------------------------------------------------------------------------

def create_draft(
    interview_id: int,
    platform: str,
    draft_text: str,
    hook: str | None = None,
    topic: str | None = None,
) -> ContentDraft:
    """Create a new content draft for review."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO content_drafts (interview_id, platform, draft_text, hook, topic)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (interview_id, platform, draft_text, hook, topic),
            )
            conn.commit()
            return _row_to_draft(cur.fetchone())
    finally:
        conn.close()


def update_draft_slack_ts(draft_id: int, slack_channel: str, slack_ts: str) -> None:
    """Store the Slack message timestamp so we can track reactions."""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE content_drafts SET slack_channel = %s, slack_ts = %s WHERE id = %s",
                (slack_channel, slack_ts, draft_id),
            )
            conn.commit()
    finally:
        conn.close()


def get_draft_by_slack_ts(slack_ts: str) -> ContentDraft | None:
    """Find a draft by its Slack message timestamp (for reaction handling)."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM content_drafts WHERE slack_ts = %s", (slack_ts,)
            )
            row = cur.fetchone()
            return _row_to_draft(row) if row else None
    finally:
        conn.close()


def approve_draft(draft_id: int) -> ContentDraft:
    """Approve a draft for posting."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE content_drafts
                SET status = 'approved', approved_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (draft_id,),
            )
            conn.commit()
            return _row_to_draft(cur.fetchone())
    finally:
        conn.close()


def reject_draft(draft_id: int) -> ContentDraft:
    """Reject a draft."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE content_drafts
                SET status = 'rejected'
                WHERE id = %s
                RETURNING *
                """,
                (draft_id,),
            )
            conn.commit()
            return _row_to_draft(cur.fetchone())
    finally:
        conn.close()


def get_drafts_for_interview(interview_id: int) -> list[ContentDraft]:
    """Get all drafts created from an interview."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM content_drafts WHERE interview_id = %s ORDER BY platform, id",
                (interview_id,),
            )
            return [_row_to_draft(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_approved_drafts() -> list[ContentDraft]:
    """Get all approved drafts ready to post."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM content_drafts WHERE status = 'approved' ORDER BY created_at ASC"
            )
            return [_row_to_draft(row) for row in cur.fetchall()]
    finally:
        conn.close()
