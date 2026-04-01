"""Content pipeline — weekly interview, trend research, and post drafting.

Flow:
1. Bot initiates a weekly interview via Slack DM (5 adaptive questions)
2. After the interview, researches trending topics in entrepreneurship/AI
3. Drafts platform-specific posts (X + LinkedIn) combining answers + trends
4. Sends drafts to Slack for emoji-based approval
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from config.constants import (
    CONTENT_MODEL,
    CONTENT_OWNER_SLACK_USER,
    CONTENT_INTERVIEW_DAY,
    CONTENT_INTERVIEW_HOUR,
    INTERVIEW_QUESTION_COUNT,
    INTERVIEW_STALE_HOURS,
    MAX_CONTENT_TOKENS,
    CONTENT_TOPICS,
)
from models.content import (
    Interview,
    create_interview,
    get_active_interview,
    get_last_completed_interview,
    add_question_to_interview,
    record_answer,
    complete_interview,
    cancel_interview,
    create_draft,
    update_draft_slack_ts,
)
from models.idea import get_recent_ideas
from services.slack_notify import (
    send_interview_start,
    send_interview_question,
    send_interview_complete,
    send_content_draft,
    send_drafts_complete,
    dm_user,
)

load_dotenv()
logger = logging.getLogger(__name__)

INTERVIEW_PROMPT = (Path(__file__).parent / "prompts" / "interview.md").read_text()
DRAFT_PROMPT = (Path(__file__).parent / "prompts" / "content_draft.md").read_text()

# Day name → weekday number (Monday=0)
_DAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


# ---------------------------------------------------------------------------
# Scheduling — checks if it's time for the weekly interview
# ---------------------------------------------------------------------------

def check_and_start_interview() -> None:
    """Called by the content loop. Starts an interview if it's time."""
    if not CONTENT_OWNER_SLACK_USER:
        return  # Feature disabled

    _cancel_stale_interviews()

    now = datetime.now(timezone.utc)

    # Check day of week
    target_day = _DAY_MAP.get(CONTENT_INTERVIEW_DAY, 0)
    if now.weekday() != target_day:
        return

    # Check hour (within the target hour window)
    if now.hour != CONTENT_INTERVIEW_HOUR:
        return

    # Check if there's already an active interview
    active = get_active_interview(CONTENT_OWNER_SLACK_USER)
    if active:
        return

    # Check if last interview was too recent (less than 6 days ago)
    last = get_last_completed_interview(CONTENT_OWNER_SLACK_USER)
    if last and last.completed_at:
        days_since = (now - last.completed_at).days
        if days_since < 6:
            return

    # Time to start!
    start_interview(CONTENT_OWNER_SLACK_USER)


def _cancel_stale_interviews() -> None:
    """Auto-cancel interviews that have been active for too long."""
    active = get_active_interview(CONTENT_OWNER_SLACK_USER)
    if not active:
        return

    age_hours = (datetime.now(timezone.utc) - active.created_at).total_seconds() / 3600
    if age_hours > INTERVIEW_STALE_HOURS:
        logger.info("Auto-cancelling stale interview %d (%.1f hours old)", active.id, age_hours)
        cancel_interview(active.id)


# ---------------------------------------------------------------------------
# Interview — start + handle answers
# ---------------------------------------------------------------------------

def start_interview(slack_user: str) -> None:
    """Kick off a new weekly content interview by DMing the user."""
    client = _get_slack_client()

    # Open a DM channel with the user
    resp = client.conversations_open(users=[slack_user])
    channel = resp["channel"]["id"]

    # Send the opening message as a new thread
    thread_resp = client.chat_postMessage(
        channel=channel,
        text="Time for your weekly content session!",
    )
    thread_ts = thread_resp["ts"]

    # Create interview record
    interview = create_interview(slack_user, channel, thread_ts)
    logger.info("Started content interview %d for user %s", interview.id, slack_user)

    # Send the intro message in the thread
    send_interview_start(channel, thread_ts)

    # Generate and send the first question
    _generate_and_send_question(interview)


def handle_interview_answer(interview: Interview, answer_text: str) -> None:
    """Process a user's answer and either ask the next question or finish."""
    # Figure out which question they're answering (the last one asked)
    answer_index = len(interview.questions) - 1
    if answer_index < 0:
        logger.warning("Received answer but no questions asked yet for interview %d", interview.id)
        return

    # Skip if this question already has an answer
    if interview.questions[answer_index].get("answer"):
        logger.info("Question %d already answered, ignoring duplicate", answer_index)
        return

    # Record the answer
    interview = record_answer(interview.id, answer_index, answer_text)
    logger.info("Recorded answer %d/%d for interview %d", answer_index + 1, INTERVIEW_QUESTION_COUNT, interview.id)

    # Check if we have all answers
    answered_count = sum(1 for q in interview.questions if q.get("answer"))
    if answered_count >= INTERVIEW_QUESTION_COUNT:
        # Interview complete — kick off the content pipeline
        send_interview_complete(interview.slack_channel, interview.slack_thread_ts)
        _run_content_pipeline(interview)
    else:
        # Generate and send the next question
        _generate_and_send_question(interview)


def _generate_and_send_question(interview: Interview) -> None:
    """Use Claude to generate an adaptive follow-up question, then send it."""
    question_number = len(interview.questions) + 1

    # Build context from recent ideas
    recent_ideas = get_recent_ideas(limit=10)
    ideas_context = "\n".join(
        f"- {idea.title or idea.raw_text[:100]}" for idea in recent_ideas
    ) or "No recent ideas captured."

    # Build previous Q&A context
    prev_qa = ""
    for i, qa in enumerate(interview.questions):
        prev_qa += f"Q{i+1}: {qa['question']}\n"
        if qa.get("answer"):
            prev_qa += f"A{i+1}: {qa['answer']}\n\n"
    prev_qa = prev_qa.strip() or "This is the first question."

    # Generate question using Claude
    prompt = INTERVIEW_PROMPT.replace("{question_number}", str(question_number))
    prompt = prompt.replace("{total_questions}", str(INTERVIEW_QUESTION_COUNT))
    prompt = prompt.replace("{content_topics}", ", ".join(CONTENT_TOPICS))
    prompt = prompt.replace("{recent_ideas}", ideas_context)
    prompt = prompt.replace("{previous_qa}", prev_qa)

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CONTENT_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    question_text = response.content[0].text.strip()

    # Save the question and send it
    add_question_to_interview(interview.id, question_text)
    send_interview_question(
        interview.slack_channel,
        interview.slack_thread_ts,
        question_number,
        INTERVIEW_QUESTION_COUNT,
        question_text,
    )


# ---------------------------------------------------------------------------
# Content pipeline — trend research + draft generation
# ---------------------------------------------------------------------------

def _run_content_pipeline(interview: Interview) -> None:
    """Research trends, draft posts, send for review."""
    try:
        # Step 1: Research trending topics
        trends = _research_trends()
        interview = complete_interview(interview.id, trends_json=trends)
        logger.info("Trend research complete for interview %d", interview.id)

        # Step 2: Draft posts for each platform
        interview_qa = _format_interview_qa(interview)
        trending_text = _format_trends(trends)

        draft_count = 0
        for platform, count in [("x", 2), ("linkedin", 2)]:
            drafts = _generate_drafts(interview_qa, trending_text, platform, count)
            for draft_data in drafts:
                draft = create_draft(
                    interview_id=interview.id,
                    platform=platform,
                    draft_text=draft_data["draft_text"],
                    hook=draft_data.get("hook"),
                    topic=draft_data.get("topic"),
                )
                # Send to Slack and save the message timestamp
                slack_ts = send_content_draft(
                    interview.slack_channel,
                    platform,
                    draft_data["draft_text"],
                    draft_data.get("hook"),
                )
                if slack_ts:
                    update_draft_slack_ts(draft.id, interview.slack_channel, slack_ts)
                draft_count += 1

        # Step 3: Send summary
        send_drafts_complete(interview.slack_channel, draft_count)
        logger.info("Content pipeline complete: %d drafts sent for interview %d", draft_count, interview.id)

    except Exception:
        logger.exception("Content pipeline failed for interview %d", interview.id)
        dm_user(
            interview.slack_user,
            "Something went wrong drafting your posts. I'll try again next time.",
        )


def _research_trends() -> dict:
    """Use Claude + web search to find trending topics in entrepreneurship/AI."""
    client = anthropic.Anthropic()

    trend_prompt = (
        "Search for what is currently trending and getting engagement on X (Twitter) "
        "and LinkedIn in these topics: entrepreneurship, AI, startups, building in public, "
        "solo founding.\n\n"
        "For each platform, find 3-4 specific trending topics, conversations, or themes "
        "that are getting attention RIGHT NOW.\n\n"
        "Return a JSON object with this structure:\n"
        "```json\n"
        "{\n"
        '  "x_trends": [\n'
        '    {"topic": "...", "context": "...", "why_engaging": "..."}\n'
        "  ],\n"
        '  "linkedin_trends": [\n'
        '    {"topic": "...", "context": "...", "why_engaging": "..."}\n'
        "  ],\n"
        '  "cross_platform_themes": ["...", "..."]\n'
        "}\n"
        "```\n"
        "Be specific — name actual conversations, posts, or themes you find, "
        "not generic topics like 'AI is growing'."
    )

    response = client.messages.create(
        model=CONTENT_MODEL,
        max_tokens=MAX_CONTENT_TOKENS,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        messages=[{"role": "user", "content": trend_prompt}],
    )

    # Extract text from response (may contain web search result blocks too)
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    # Parse JSON from response
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        logger.warning("Could not parse trend research JSON, using raw text")
        return {"raw_trends": text, "x_trends": [], "linkedin_trends": [], "cross_platform_themes": []}


def _generate_drafts(interview_qa: str, trending_text: str, platform: str, count: int) -> list[dict]:
    """Generate post drafts for a specific platform."""
    client = anthropic.Anthropic()

    prompt = DRAFT_PROMPT.replace("{platform}", "X (Twitter)" if platform == "x" else "LinkedIn")
    prompt = prompt.replace("{post_count}", str(count))
    prompt = prompt.replace("{interview_qa}", interview_qa)
    prompt = prompt.replace("{trending_topics}", trending_text)

    response = client.messages.create(
        model=CONTENT_MODEL,
        max_tokens=MAX_CONTENT_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text

    # Parse JSON
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        drafts = json.loads(text.strip())
        if isinstance(drafts, list):
            return drafts[:count]
        return []
    except json.JSONDecodeError:
        logger.warning("Could not parse draft JSON for %s", platform)
        return [{"draft_text": text.strip(), "hook": None, "topic": "general"}]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_interview_qa(interview: Interview) -> str:
    """Format the interview Q&A pairs as readable text for the drafting prompt."""
    lines = []
    for i, qa in enumerate(interview.questions):
        lines.append(f"Q{i+1}: {qa['question']}")
        lines.append(f"A{i+1}: {qa.get('answer', '(no answer)')}")
        lines.append("")
    return "\n".join(lines)


def _format_trends(trends: dict) -> str:
    """Format trend research results as readable text for the drafting prompt."""
    lines = []

    for trend in trends.get("x_trends", []):
        lines.append(f"- [X] {trend.get('topic', '?')}: {trend.get('context', '')}")

    for trend in trends.get("linkedin_trends", []):
        lines.append(f"- [LinkedIn] {trend.get('topic', '?')}: {trend.get('context', '')}")

    themes = trends.get("cross_platform_themes", [])
    if themes:
        lines.append(f"\nCross-platform themes: {', '.join(themes)}")

    # Fallback if trends parsing failed
    if not lines and trends.get("raw_trends"):
        lines.append(trends["raw_trends"])

    return "\n".join(lines) or "No specific trends found this week."


def _get_slack_client():
    """Get the shared Slack WebClient."""
    # Import here to reuse the singleton from slack_notify
    from services.slack_notify import _get_client
    return _get_client()
