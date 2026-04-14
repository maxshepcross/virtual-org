"""Post founder-facing attention items and approvals to Slack."""

from __future__ import annotations

import os
import time

from config.env import load_project_env
from models.control_plane import (
    ApprovalRequest,
    AttentionItem,
    list_unposted_approval_requests,
    list_unposted_attention_items,
    mark_approval_request_posted,
    mark_attention_item_posted,
    update_agent_run,
)
from models.task import get_task, update_task_slack_route
from services.slack_api import SlackApiClient, SlackApiError


class SlackDispatcherError(SlackApiError):
    """Raised when Slack delivery fails."""


def _format_attention_item(item: AttentionItem) -> str:
    headline = f"[{item.severity.upper()}] {item.headline}"
    lines = [headline]
    if item.task_id is not None:
        lines.append(f"Task: {item.task_id}")
    if item.agent_run_id is not None:
        lines.append(f"Run: {item.agent_run_id}")
    if item.venture:
        lines.append(f"Venture: {item.venture}")
    lines.append(f"Bucket: {item.bucket}")
    lines.append(f"Recommended action: {item.recommended_action}")
    return "\n".join(lines)


def _format_approval_request(request: ApprovalRequest) -> str:
    lines = [
        f"[APPROVAL NEEDED] {request.action_type}",
        f"Approval ID: {request.id}",
        f"Task: {request.task_id}",
        f"Run: {request.agent_run_id}" if request.agent_run_id is not None else "Run: not attached",
        f"Target: {request.target_summary}",
        "Review the request in the control plane and approve or deny it.",
    ]
    return "\n".join(lines)


def _approval_request_blocks(request: ApprovalRequest) -> list[dict]:
    value_prefix = f"{request.id}:"
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": _format_approval_request(request),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "action_id": "approval_approve",
                    "value": f"{value_prefix}approved",
                },
                {
                    "type": "button",
                    "style": "danger",
                    "text": {"type": "plain_text", "text": "Deny"},
                    "action_id": "approval_deny",
                    "value": f"{value_prefix}denied",
                    "confirm": {
                        "title": {"type": "plain_text", "text": "Deny this action?"},
                        "text": {"type": "mrkdwn", "text": "This will block the action until someone creates a new approval request."},
                        "confirm": {"type": "plain_text", "text": "Deny"},
                        "deny": {"type": "plain_text", "text": "Cancel"},
                    },
                },
            ],
        },
    ]


def _should_claim_task_thread(task_id: int | None, provided_thread_ts: str | None) -> bool:
    if task_id is None or provided_thread_ts:
        return False
    task = get_task(task_id)
    return bool(task) and not task.slack_thread_ts


def dispatch_once(limit: int = 25) -> dict[str, int]:
    load_project_env()
    bot_token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    if not bot_token:
        raise SlackDispatcherError("SLACK_BOT_TOKEN is not configured in .env.")

    attention_items = list_unposted_attention_items(limit=limit)
    approvals = list_unposted_approval_requests(limit=limit)

    sent_attention = 0
    sent_approvals = 0
    client = SlackApiClient(bot_token)
    try:
        for item in attention_items:
            if not item.slack_channel_id:
                continue
            result = client.post_message(
                channel=item.slack_channel_id,
                thread_ts=item.slack_thread_ts,
                text=_format_attention_item(item),
            )
            mark_attention_item_posted(item.id, slack_message_ts=result.ts)
            if item.agent_run_id is not None:
                update_agent_run(
                    item.agent_run_id,
                    slack_channel_id=result.channel,
                    slack_thread_ts=item.slack_thread_ts or result.ts,
                )
            if result.ts and _should_claim_task_thread(item.task_id, item.slack_thread_ts):
                update_task_slack_route(
                    item.task_id,
                    slack_channel_id=result.channel,
                    slack_thread_ts=result.ts,
                )
            sent_attention += 1

        for request in approvals:
            if not request.requested_slack_channel_id:
                continue
            result = client.post_message(
                channel=request.requested_slack_channel_id,
                thread_ts=request.requested_slack_thread_ts,
                text=_format_approval_request(request),
                blocks=_approval_request_blocks(request),
            )
            mark_approval_request_posted(request.id, slack_message_ts=result.ts)
            if request.agent_run_id is not None:
                update_agent_run(
                    request.agent_run_id,
                    slack_channel_id=result.channel,
                    slack_thread_ts=request.requested_slack_thread_ts or result.ts,
                )
            if result.ts and _should_claim_task_thread(request.task_id, request.requested_slack_thread_ts):
                update_task_slack_route(
                    request.task_id,
                    slack_channel_id=result.channel,
                    slack_thread_ts=result.ts,
                )
            sent_approvals += 1
    finally:
        client.close()

    return {
        "attention_items_sent": sent_attention,
        "approval_requests_sent": sent_approvals,
    }


def run_forever() -> None:
    load_project_env()
    interval_seconds = int(os.getenv("SLACK_DISPATCH_INTERVAL_SECONDS", "10"))
    while True:
        try:
            dispatch_once()
        except Exception as exc:  # pragma: no cover - service loop logging path
            print(f"Slack dispatcher error: {exc}", flush=True)
        time.sleep(max(2, interval_seconds))
