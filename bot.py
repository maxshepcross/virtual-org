#!/usr/bin/env python3
"""Slack bot — captures ideas via DM using Socket Mode (no public URL needed).

Also runs the triage loop in a background thread.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from config.constants import TRIAGE_INTERVAL_SECONDS
from models.idea import create_idea
from services.slack_notify import notify_idea_captured
from triage import run_triage

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)


# ---------------------------------------------------------------------------
# Message handler — captures any DM as an idea
# ---------------------------------------------------------------------------

@app.event("message")
def handle_message(event, say):
    """Capture any DM to the bot as a raw idea."""
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
# Main
# ---------------------------------------------------------------------------

def main():
    # Start triage in background
    triage_thread = threading.Thread(target=_triage_loop, daemon=True)
    triage_thread.start()
    logger.info("Triage loop started (every %ds)", TRIAGE_INTERVAL_SECONDS)

    # Start Slack bot via Socket Mode
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    logger.info("Virtual Org bot starting (Socket Mode)...")
    handler.start()


if __name__ == "__main__":
    main()
