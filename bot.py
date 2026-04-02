#!/usr/bin/env python3
"""Slack bot — captures ideas via DM using Socket Mode (no public URL needed).

Also runs the triage loop and content interview scheduling in background threads.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from config.env import load_project_env
from config.constants import TRIAGE_INTERVAL_SECONDS, CONTENT_CHECK_INTERVAL_SECONDS
from content_pipeline import check_and_start_interview, handle_interview_answer
from models.content import get_active_interview, get_draft_by_slack_ts, approve_draft, reject_draft
from models.idea import create_idea
from services.slack_notify import notify_idea_captured, reply_in_thread
from triage import run_triage

load_project_env()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)


# ---------------------------------------------------------------------------
# Message handler — routes to interview or idea capture
# ---------------------------------------------------------------------------

@app.event("message")
def handle_message(event, say):
    """Route DMs: interview responses go to the content pipeline, everything else is an idea."""
    # Only handle DMs (im channel type) and ignore bot messages
    channel_type = event.get("channel_type")
    if channel_type != "im":
        return
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return

    text = event.get("text", "")
    ts = event.get("ts")
    channel = event.get("channel")
    user = event.get("user")
    thread_ts = event.get("thread_ts") or ts

    # --- Check for active content interview first ---
    # If the user is replying in an interview thread, route to the interview handler.
    # Messages outside the interview thread are still captured as ideas.
    if text and user:
        interview = get_active_interview(user)
        if interview and interview.slack_channel == channel:
            # Match if replying in the interview thread OR if it's a top-level DM
            # while an interview is active (user might not click "reply in thread")
            if thread_ts == interview.slack_thread_ts or event.get("thread_ts") is None:
                try:
                    handle_interview_answer(interview, text)
                except Exception:
                    logger.exception("Failed to handle interview answer")
                    say(text="Sorry, something went wrong. Try answering again?", thread_ts=interview.slack_thread_ts)
                return

    # --- Normal idea capture ---
    # Check for file attachments (voice memos, images)
    files = event.get("files", [])
    image_url = None
    voice_transcript = None

    for f in files:
        mimetype = f.get("mimetype", "")
        if mimetype.startswith("image/"):
            image_url = f.get("url_private")
        elif mimetype.startswith("audio/") or mimetype.startswith("video/"):
            # For voice memos, we'll transcribe async later.
            # For now, store the URL and add a note.
            image_url = f.get("url_private")  # Reuse field for now
            if not text:
                text = "[Voice memo — transcription pending]"

    if not text and not files:
        return

    try:
        create_idea(
            raw_text=text,
            slack_ts=ts,
            slack_thread_ts=thread_ts,
            slack_channel=channel,
            slack_user=user,
            raw_image_url=image_url,
            voice_transcript=voice_transcript,
        )
        notify_idea_captured(channel, thread_ts)
    except Exception:
        logger.exception("Failed to capture idea")
        say(text="Sorry, I couldn't save that. Try again?", thread_ts=thread_ts)


# ---------------------------------------------------------------------------
# Reaction handler — approves or rejects content drafts
# ---------------------------------------------------------------------------

@app.event("reaction_added")
def handle_reaction(event):
    """Handle emoji reactions on content draft messages."""
    reaction = event.get("reaction", "")
    item = event.get("item", {})
    slack_ts = item.get("ts")

    if not slack_ts:
        return

    # Check if this reaction is on a content draft message
    draft = get_draft_by_slack_ts(slack_ts)
    if not draft:
        return

    # Only process if draft is still pending
    if draft.status != "pending":
        return

    channel = item.get("channel", draft.slack_channel)

    if reaction in ("white_check_mark", "heavy_check_mark", "+1", "thumbsup"):
        approve_draft(draft.id)
        logger.info("Draft %d approved (platform: %s)", draft.id, draft.platform)
        reply_in_thread(channel, slack_ts, "Approved! Ready to post.")

    elif reaction in ("x", "no_entry", "-1", "thumbsdown"):
        reject_draft(draft.id)
        logger.info("Draft %d rejected (platform: %s)", draft.id, draft.platform)
        reply_in_thread(channel, slack_ts, "Skipped.")


# ---------------------------------------------------------------------------
# Triage loop — runs in background thread
# ---------------------------------------------------------------------------

def _triage_loop():
    """Periodically triage raw ideas."""
    while True:
        try:
            count = run_triage()
            if count:
                logger.info("Triage loop: processed %d idea(s)", count)
        except Exception:
            logger.exception("Triage loop error")
        time.sleep(TRIAGE_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Content loop — runs in background thread
# ---------------------------------------------------------------------------

def _content_loop():
    """Periodically check if it's time for the weekly content interview."""
    while True:
        try:
            check_and_start_interview()
        except Exception:
            logger.exception("Content loop error")
        time.sleep(CONTENT_CHECK_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Start triage in background
    triage_thread = threading.Thread(target=_triage_loop, daemon=True)
    triage_thread.start()
    logger.info("Triage loop started (every %ds)", TRIAGE_INTERVAL_SECONDS)

    # Start content interview scheduling in background
    content_thread = threading.Thread(target=_content_loop, daemon=True)
    content_thread.start()
    logger.info("Content loop started (checking every %ds)", CONTENT_CHECK_INTERVAL_SECONDS)

    # Start Slack bot via Socket Mode
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    logger.info("Virtual Org bot starting (Socket Mode)...")
    handler.start()


if __name__ == "__main__":
    main()
