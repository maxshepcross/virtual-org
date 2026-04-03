"""Slack notification helpers for the workspace automation app."""

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


# ---------------------------------------------------------------------------
# Content pipeline notifications
# ---------------------------------------------------------------------------

def send_interview_start(channel: str, thread_ts: str) -> None:
    """Send the opening message for a weekly content interview."""
    reply_in_thread(
        channel,
        thread_ts,
        "Hey! Time for your weekly content session.\n"
        "I'll ask you 5 quick questions to pull out stories and ideas for posts this week.\n"
        "Just reply in this thread — takes about 5 minutes.",
    )


def send_interview_question(
    channel: str, thread_ts: str, question_number: int, total: int, question_text: str
) -> None:
    """Send a numbered interview question."""
    reply_in_thread(
        channel,
        thread_ts,
        f"*Question {question_number}/{total}*\n{question_text}",
    )


def send_interview_complete(channel: str, thread_ts: str) -> None:
    """Confirm the interview is done and drafts are coming."""
    reply_in_thread(
        channel,
        thread_ts,
        "Great answers! I'll research what's trending and draft some posts. "
        "Give me a few minutes.",
    )


def send_content_draft(channel: str, platform: str, draft_text: str, hook: str | None = None) -> str | None:
    """Send a content draft for review. Returns the message ts for reaction tracking."""
    platform_label = "X (Twitter)" if platform == "x" else "LinkedIn"
    text = (
        f"*Draft for {platform_label}*\n\n"
        f"{draft_text}\n\n"
        "---\n"
        "React with :white_check_mark: to approve or :x: to skip."
    )
    try:
        resp = _get_client().chat_postMessage(channel=channel, text=text)
        return resp["ts"]
    except Exception:
        logger.exception("Failed to send content draft")
        return None


def send_drafts_complete(channel: str, count: int) -> None:
    """Notify that all drafts have been sent."""
    try:
        _get_client().chat_postMessage(
            channel=channel,
            text=f"I've sent you {count} draft posts above. "
            "React with :white_check_mark: on the ones you want to post!",
        )
    except Exception:
        logger.exception("Failed to send drafts-complete notification")
