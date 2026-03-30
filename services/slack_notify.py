"""Slack notification helpers for Virtual Org."""

from __future__ import annotations

import logging
import os

from slack_sdk import WebClient

logger = logging.getLogger(__name__)

_client: WebClient | None = None


def _get_client() -> WebClient:
    global _client
    if _client is None:
        token = os.environ.get("SLACK_BOT_TOKEN")
        if not token:
            raise RuntimeError("SLACK_BOT_TOKEN not set")
        _client = WebClient(token=token)
    return _client


def reply_in_thread(channel: str, thread_ts: str, text: str) -> None:
    """Reply in the same Slack thread as the original idea."""
    try:
        _get_client().chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=text,
        )
    except Exception:
        logger.exception("Failed to send Slack thread reply")


def dm_user(user_id: str, text: str) -> None:
    """Send a DM to a specific user."""
    try:
        client = _get_client()
        resp = client.conversations_open(users=[user_id])
        channel = resp["channel"]["id"]
        client.chat_postMessage(channel=channel, text=text)
    except Exception:
        logger.exception("Failed to send Slack DM")


def notify_idea_captured(channel: str, thread_ts: str) -> None:
    reply_in_thread(channel, thread_ts, "Captured. I'll triage this shortly.")


def notify_idea_triaged(
    channel: str,
    thread_ts: str,
    title: str,
    category: str,
    effort: str,
    impact: str,
    will_action: bool,
) -> None:
    action_line = "I'll start working on this." if will_action else "Saved for your review."
    reply_in_thread(
        channel,
        thread_ts,
        f"*Triaged:* *{title}*\n"
        f"Category: {category} | Effort: {effort} | Impact: {impact}\n"
        f"{action_line}",
    )


def notify_research_done(channel: str, thread_ts: str, title: str, summary: str) -> None:
    reply_in_thread(
        channel,
        thread_ts,
        f"*Research complete:* *{title}*\n{summary}\nImplementing now.",
    )


def notify_pr_opened(
    channel: str, thread_ts: str, title: str, pr_url: str, repo: str, pr_number: int
) -> None:
    reply_in_thread(
        channel,
        thread_ts,
        f"*PR ready for review:* *{title}*\n<{pr_url}|{repo}#{pr_number}>",
    )


def notify_task_failed(channel: str, thread_ts: str, title: str, error: str) -> None:
    reply_in_thread(
        channel,
        thread_ts,
        f"*Failed:* *{title}*\n{error}\nNeeds your input.",
    )
