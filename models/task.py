"""Task data model for queued studio work.

Uses atomic claiming with FOR UPDATE SKIP LOCKED, lease-based heartbeating,
and an append-only event log.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras
from pydantic import BaseModel, Field

from config.constants import LEASE_SECONDS, TASK_STATUSES_FINAL


class Task(BaseModel):
    id: int | None = None
    idea_id: int | None = None

    title: str
    description: str
    category: str
    target_repo: str | None = None
    venture: str | None = None
    requested_by: str | None = None

    status: str = "queued"
    worker_id: str | None = None
    lease_token: str | None = None
    lease_expires_at: datetime | None = None
    last_heartbeat_at: datetime | None = None

    research_json: dict[str, Any] | None = None
    execution_stories_json: list[dict[str, Any]] | None = None
    implementation_json: dict[str, Any] | None = None
    progress_notes_json: list[dict[str, Any]] | None = None
    verification_json: list[dict[str, Any]] | None = None
    current_story_id: str | None = None
    pr_url: str | None = None
    pr_number: int | None = None
    pr_status: str | None = None
    branch_name: str | None = None
    slack_channel_id: str | None = None
    slack_thread_ts: str | None = None
    approval_state: str | None = None
    latest_attention_severity: str | None = None
    error_message: str | None = None

    events: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None


def _conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def _row_to_task(row: dict) -> Task:
    for field in (
        "research_json",
        "execution_stories_json",
        "implementation_json",
        "progress_notes_json",
        "verification_json",
        "events",
    ):
        if row.get(field) and isinstance(row[field], str):
            row[field] = json.loads(row[field])
    return Task(**row)


def create_task(
    idea_id: int | None,
    title: str,
    description: str,
    category: str,
    target_repo: str | None = None,
    venture: str | None = None,
    requested_by: str | None = None,
    slack_channel_id: str | None = None,
    slack_thread_ts: str | None = None,
) -> Task:
    """Create a new queued task."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            initial_event = json.dumps([{
                "type": "queued",
                "at": datetime.now(timezone.utc).isoformat(),
                "message": f"Task created{f' from idea #{idea_id}' if idea_id else ''}",
            }])
            cur.execute(
                """
                INSERT INTO tasks (
                    idea_id,
                    title,
                    description,
                    category,
                    target_repo,
                    venture,
                    requested_by,
                    slack_channel_id,
                    slack_thread_ts,
                    events
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    idea_id,
                    title,
                    description,
                    category,
                    target_repo,
                    venture,
                    requested_by,
                    slack_channel_id,
                    slack_thread_ts,
                    initial_event,
                ),
            )
            conn.commit()
            return _row_to_task(cur.fetchone())
    finally:
        conn.close()


def claim_next_task(worker_id: str) -> Task | None:
    """Atomically claim the next queued task. Returns None if queue is empty."""
    conn = _conn()
    lease_token = str(uuid.uuid4())
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                WITH candidate AS (
                    SELECT id FROM tasks
                    WHERE status = 'queued'
                    ORDER BY created_at ASC, id ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE tasks t
                SET status = 'claimed',
                    worker_id = %s,
                    lease_token = %s,
                    lease_expires_at = NOW() + INTERVAL '%s seconds',
                    last_heartbeat_at = NOW(),
                    started_at = NOW()
                FROM candidate c
                WHERE t.id = c.id
                RETURNING t.*
                """,
                (worker_id, lease_token, LEASE_SECONDS),
            )
            conn.commit()
            row = cur.fetchone()
            return _row_to_task(row) if row else None
    finally:
        conn.close()


def heartbeat_task(task_id: int, lease_token: str) -> None:
    """Extend the lease on a claimed task."""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tasks
                SET last_heartbeat_at = NOW(),
                    lease_expires_at = NOW() + INTERVAL '%s seconds'
                WHERE id = %s AND lease_token = %s
                """,
                (LEASE_SECONDS, task_id, lease_token),
            )
            conn.commit()
            if cur.rowcount == 0:
                raise ValueError(f"Heartbeat failed: task {task_id} lease mismatch")
    finally:
        conn.close()


def update_task_status(
    task_id: int,
    lease_token: str,
    status: str,
    event_message: str = "",
    **fields,
) -> Task:
    """Transition task to a new status with an event log entry."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Append event
            new_event = json.dumps({
                "type": status,
                "at": datetime.now(timezone.utc).isoformat(),
                "message": event_message,
            })

            # Build dynamic SET clause for extra fields
            set_parts = ["status = %s", "events = events || %s::jsonb"]
            params: list[Any] = [status, new_event]

            if status in ("done", "failed", "pr_open"):
                set_parts.append("finished_at = NOW()")

            for key, value in fields.items():
                if key in (
                    "research_json",
                    "execution_stories_json",
                    "implementation_json",
                    "progress_notes_json",
                    "verification_json",
                ):
                    set_parts.append(f"{key} = %s")
                    params.append(json.dumps(value))
                elif key in (
                    "pr_url",
                    "pr_number",
                    "pr_status",
                    "branch_name",
                    "error_message",
                    "current_story_id",
                ):
                    set_parts.append(f"{key} = %s")
                    params.append(value)

            params.extend([task_id, lease_token])

            cur.execute(
                f"""
                UPDATE tasks
                SET {', '.join(set_parts)}
                WHERE id = %s AND lease_token = %s
                RETURNING *
                """,
                params,
            )
            conn.commit()
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Status update failed: task {task_id} lease mismatch")
            return _row_to_task(row)
    finally:
        conn.close()


def fail_stale_tasks() -> list[Task]:
    """Auto-fail tasks whose lease has expired (worker crashed)."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            stale_event = json.dumps({
                "type": "failed",
                "at": datetime.now(timezone.utc).isoformat(),
                "message": "Stale lease — worker disappeared",
            })
            cur.execute(
                """
                UPDATE tasks
                SET status = 'failed',
                    error_message = 'stale_lease',
                    finished_at = NOW(),
                    events = events || %s::jsonb
                WHERE status IN ('claimed', 'researching', 'implementing')
                  AND lease_expires_at < NOW()
                RETURNING *
                """,
                (stale_event,),
            )
            conn.commit()
            return [_row_to_task(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_task(task_id: int) -> Task | None:
    """Fetch a single task by ID."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()
            return _row_to_task(row) if row else None
    finally:
        conn.close()


def get_active_tasks() -> list[Task]:
    """Fetch all non-final tasks."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM tasks
                WHERE status NOT IN %s
                ORDER BY created_at ASC
                """
                ,
                (tuple(TASK_STATUSES_FINAL),)
            )
            return [_row_to_task(row) for row in cur.fetchall()]
    finally:
        conn.close()


def update_task_slack_route(task_id: int, *, slack_channel_id: str, slack_thread_ts: str) -> Task | None:
    """Store the Slack route for a task so later messages can reuse the same thread."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE tasks
                SET slack_channel_id = %s,
                    slack_thread_ts = %s
                WHERE id = %s
                RETURNING *
                """,
                (slack_channel_id, slack_thread_ts, task_id),
            )
            conn.commit()
            row = cur.fetchone()
            return _row_to_task(row) if row else None
    finally:
        conn.close()


def complete_manual_verification(
    task_id: int,
    story_id: str | None = None,
    note: str = "",
) -> Task:
    """Mark a story waiting on manual review as complete."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM tasks WHERE id = %s FOR UPDATE", (task_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Task {task_id} not found")

            task = _row_to_task(row)
            stories = list(task.execution_stories_json or [])
            if not stories:
                raise ValueError(f"Task {task_id} has no execution stories")

            target_story = None
            for story in stories:
                if story.get("status") != "awaiting_manual_verification":
                    continue
                if story_id is None or story.get("id") == story_id:
                    target_story = story
                    break

            if not target_story:
                raise ValueError("No story is waiting on manual verification")

            target_story["status"] = "completed"
            next_story = next(
                (
                    story for story in sorted(
                        stories,
                        key=lambda item: (item.get("priority", 999), item.get("id", "")),
                    )
                    if story.get("status") == "pending"
                ),
                None,
            )

            progress_notes = list(task.progress_notes_json or [])
            progress_notes.append(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "story_id": target_story.get("id"),
                    "story_title": target_story.get("title"),
                    "status": "completed",
                    "message": note or "Manual verification completed.",
                }
            )

            verification = list(task.verification_json or [])
            verification.append(
                {
                    "story_id": target_story.get("id"),
                    "story_title": target_story.get("title"),
                    "at": datetime.now(timezone.utc).isoformat(),
                    "results": [
                        {
                            "step": "Manual verification",
                            "status": "passed",
                            "details": note or "Manual verification completed.",
                        }
                    ],
                }
            )

            event_message = (
                f"Manual verification completed for {target_story.get('id')}: "
                f"{target_story.get('title')}"
            )
            cur.execute(
                """
                UPDATE tasks
                SET status = 'implementing',
                    execution_stories_json = %s,
                    progress_notes_json = %s,
                    verification_json = %s,
                    current_story_id = %s,
                    events = events || %s::jsonb
                WHERE id = %s
                RETURNING *
                """,
                (
                    json.dumps(stories),
                    json.dumps(progress_notes),
                    json.dumps(verification),
                    next_story.get("id") if next_story else None,
                    json.dumps(
                        {
                            "type": "implementing",
                            "at": datetime.now(timezone.utc).isoformat(),
                            "message": event_message,
                        }
                    ),
                    task_id,
                ),
            )
            conn.commit()
            return _row_to_task(cur.fetchone())
    finally:
        conn.close()


def get_latest_task_for_title(title: str) -> Task | None:
    """Fetch the most recent task for a given title, if one exists."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM tasks
                WHERE title = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (title,),
            )
            row = cur.fetchone()
            return _row_to_task(row) if row else None
    finally:
        conn.close()


def get_recent_tasks(limit: int = 25) -> list[Task]:
    """Fetch recent tasks for duplicate and retry checks."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM tasks
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [_row_to_task(row) for row in cur.fetchall()]
    finally:
        conn.close()
