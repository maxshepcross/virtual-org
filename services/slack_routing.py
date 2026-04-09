"""Helpers for choosing where founder-facing Slack messages should go."""

from __future__ import annotations

import os

from models.task import get_task


def resolve_slack_route(
    *,
    task_id: int | None,
    explicit_channel_id: str | None = None,
    explicit_thread_ts: str | None = None,
) -> tuple[str | None, str | None]:
    """Return the best available Slack destination for a signal or approval.

    Priority:
    1. Explicit values passed by the caller.
    2. Task-level Slack route already stored on the task.
    3. One default founder channel from the environment.
    """

    if explicit_channel_id and explicit_thread_ts:
        return explicit_channel_id, explicit_thread_ts

    task = get_task(task_id) if task_id is not None else None
    channel_id = explicit_channel_id or (task.slack_channel_id if task else None)
    thread_ts = explicit_thread_ts or (task.slack_thread_ts if task else None)

    if channel_id:
        return channel_id, thread_ts

    return os.getenv("SLACK_DEFAULT_CHANNEL_ID") or None, os.getenv("SLACK_DEFAULT_THREAD_TS") or None
