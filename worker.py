#!/usr/bin/env python3
"""Worker loop — claims tasks from the queue and runs them through research → implementation."""

from __future__ import annotations

import logging
import os
import platform
import time

from config.constants import POLL_INTERVAL_SECONDS, CODE_TASK_CATEGORIES
from config.env import load_project_env
from models.idea import Idea
from models.task import (
    Task,
    claim_next_task,
    fail_stale_tasks,
    heartbeat_task,
    update_task_status,
    get_task,
)
from research import run_research
from implement import run_implementation
from services.slack_notify import (
    notify_research_done,
    notify_pr_opened,
    notify_task_failed,
)

load_project_env()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WORKER_ID = f"{platform.node()}:{os.getpid()}"


def _get_idea_slack_info(task: Task) -> tuple[str | None, str | None]:
    """Look up the Slack channel and thread for notifications."""
    if not task.idea_id:
        return None, None
    from models.idea import _conn
    import psycopg2.extras
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT slack_channel, slack_ts FROM ideas WHERE id = %s",
                (task.idea_id,),
            )
            row = cur.fetchone()
            if row:
                return row["slack_channel"], row["slack_ts"]
            return None, None
    finally:
        conn.close()


def _finalize_implementation_result(
    task: Task,
    impl_result: dict,
    channel: str | None,
    thread_ts: str | None,
) -> Task:
    """Store implementation results and notify Slack on failure or PR creation."""
    pr_url = impl_result.get("pr_url")
    pr_number = impl_result.get("pr_number")
    branch_name = impl_result.get("branch_name")
    error = impl_result.get("error")

    if error:
        task = update_task_status(
            task.id, task.lease_token, "failed",
            event_message=f"Implementation failed: {error}",
            implementation_json=impl_result,
            branch_name=branch_name,
            error_message=error,
        )
        if channel and thread_ts:
            notify_task_failed(channel, thread_ts, task.title, error)
        return task

    final_status = "pr_open" if pr_url else "done"
    task = update_task_status(
        task.id, task.lease_token, final_status,
        event_message=f"PR opened: {pr_url}" if pr_url else "Implementation complete (no PR)",
        implementation_json=impl_result,
        pr_url=pr_url,
        pr_number=pr_number,
        pr_status="open" if pr_url else None,
        branch_name=branch_name,
    )

    if pr_url and channel and thread_ts:
        notify_pr_opened(
            channel, thread_ts, task.title,
            pr_url, task.target_repo, pr_number,
        )

    return task


def execute_task(task: Task) -> None:
    """Run a task through the full pipeline: research → implement → PR."""
    channel, thread_ts = _get_idea_slack_info(task)

    # --- Phase 1: Research ---
    logger.info("Researching task #%d: %s", task.id, task.title)
    update_task_status(
        task.id, task.lease_token, "researching",
        event_message="Starting research",
    )

    try:
        research_result = run_research(task)
        heartbeat_task(task.id, task.lease_token)
    except Exception as e:
        logger.exception("Research failed for task #%d", task.id)
        update_task_status(
            task.id, task.lease_token, "failed",
            event_message=f"Research failed: {e}",
            error_message=str(e),
        )
        if channel and thread_ts:
            notify_task_failed(channel, thread_ts, task.title, str(e))
        return

    task = update_task_status(
        task.id, task.lease_token, "researching",
        event_message="Research complete",
        research_json=research_result,
    )

    if channel and thread_ts:
        summary = research_result.get("summary", "Analysis complete.")
        notify_research_done(channel, thread_ts, task.title, summary)

    # --- Phase 2: Implementation (only for code tasks) ---
    if task.category not in CODE_TASK_CATEGORIES or not task.target_repo:
        update_task_status(
            task.id, task.lease_token, "done",
            event_message="Research-only task complete (no code target)",
        )
        return

    logger.info("Implementing task #%d: %s", task.id, task.title)
    update_task_status(
        task.id, task.lease_token, "implementing",
        event_message="Starting implementation",
    )

    try:
        impl_result = run_implementation(task, research_result)
        heartbeat_task(task.id, task.lease_token)
    except Exception as e:
        logger.exception("Implementation failed for task #%d", task.id)
        update_task_status(
            task.id, task.lease_token, "failed",
            event_message=f"Implementation failed: {e}",
            error_message=str(e),
        )
        if channel and thread_ts:
            notify_task_failed(channel, thread_ts, task.title, str(e))
        return

    _finalize_implementation_result(task, impl_result, channel, thread_ts)


def run_once() -> bool:
    """Claim and execute one task. Returns True if work was done."""
    # Clean up stale leases first
    stale = fail_stale_tasks()
    for t in stale:
        logger.warning("Failed stale task #%d: %s", t.id, t.title)

    task = claim_next_task(WORKER_ID)
    if not task:
        return False

    logger.info("Claimed task #%d: %s", task.id, task.title)
    try:
        execute_task(task)
    except Exception:
        logger.exception("Unexpected error executing task #%d", task.id)
        try:
            update_task_status(
                task.id, task.lease_token, "failed",
                event_message="Unexpected worker error",
                error_message="Worker crashed during execution",
            )
        except Exception:
            logger.exception("Failed to mark task #%d as failed", task.id)

    return True


def run_forever() -> None:
    """Poll for tasks forever."""
    logger.info("Worker started (id=%s, poll=%ds)", WORKER_ID, POLL_INTERVAL_SECONDS)
    while True:
        try:
            did_work = run_once()
            if not did_work:
                time.sleep(POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            logger.info("Worker shutting down.")
            break
        except Exception:
            logger.exception("Worker loop error, sleeping before retry")
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
