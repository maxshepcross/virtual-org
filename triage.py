"""Triage engine — classifies raw ideas into structured, actionable tasks."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from config.constants import ACTIONABLE_CATEGORIES, TRIAGE_MODEL, MAX_TRIAGE_TOKENS
from models.idea import (
    get_raw_ideas,
    get_recent_ideas,
    mark_idea_tasked,
    update_idea_triage,
    Idea,
)
from models.task import create_task
from services.slack_notify import notify_idea_triaged

load_dotenv()
logger = logging.getLogger(__name__)

TRIAGE_PROMPT = (Path(__file__).parent / "prompts" / "triage.md").read_text()


def _format_recent_ideas(ideas: list[Idea]) -> str:
    if not ideas:
        return "No recent ideas yet."
    lines = []
    for idea in ideas[:15]:
        lines.append(f"- [{idea.category}] {idea.title} ({idea.effort}, {idea.impact})")
    return "\n".join(lines)


def _format_raw_idea(idea: Idea) -> str:
    parts = [idea.raw_text]
    if idea.voice_transcript:
        parts.append(f"\n[Voice transcript]: {idea.voice_transcript}")
    if idea.raw_image_url:
        parts.append(f"\n[Image attached]: {idea.raw_image_url}")
    return "\n".join(parts)


def triage_idea(idea: Idea, recent: list[Idea]) -> dict:
    """Send a raw idea to Claude for triage. Returns the structured triage result."""
    client = anthropic.Anthropic()

    prompt = TRIAGE_PROMPT.replace("{recent_ideas}", _format_recent_ideas(recent))
    prompt = prompt.replace("{raw_idea}", _format_raw_idea(idea))

    response = client.messages.create(
        model=TRIAGE_MODEL,
        max_tokens=MAX_TRIAGE_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    # Strip markdown code fences if present
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    return json.loads(text.strip())


def run_triage() -> int:
    """Triage all raw ideas. Returns count of ideas triaged."""
    raw_ideas = get_raw_ideas()
    if not raw_ideas:
        return 0

    recent = get_recent_ideas()
    triaged_count = 0

    for idea in raw_ideas:
        try:
            result = triage_idea(idea, recent)

            # Update idea with triage results
            updated = update_idea_triage(
                idea_id=idea.id,
                category=result["category"],
                title=result["title"],
                structured_body=result["structured_body"],
                effort=result["effort"],
                impact=result["impact"],
                target_repo=result.get("target_repo"),
                triage_json=result,
            )

            # Create task if actionable
            will_action = result["category"] in ACTIONABLE_CATEGORIES and not result.get("duplicate_of")

            if will_action:
                create_task(
                    idea_id=idea.id,
                    title=result["title"],
                    description=result["structured_body"],
                    category=result["category"],
                    target_repo=result.get("target_repo"),
                )
                mark_idea_tasked(idea.id)

            # Notify on Slack
            if idea.slack_channel and idea.slack_ts:
                notify_idea_triaged(
                    channel=idea.slack_channel,
                    thread_ts=idea.slack_ts,
                    title=result["title"],
                    category=result["category"],
                    effort=result["effort"],
                    impact=result["impact"],
                    will_action=will_action,
                )

            triaged_count += 1
            logger.info("Triaged idea #%d: %s [%s]", idea.id, result["title"], result["category"])

        except Exception:
            logger.exception("Failed to triage idea #%d", idea.id)

    return triaged_count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = run_triage()
    print(f"Triaged {count} idea(s).")
