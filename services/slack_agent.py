"""Slack agent request verification and founder-facing command handling."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from models.control_plane import get_approval_request, get_task_control_state, list_attention_items
from services.approval_service import ApprovalResolutionRequest, get_pending_approvals, resolve_approval
from services.briefing_service import generate_briefing
from services.slack_api import SlackApiClient
from services.task_runner import TaskRunner


class SlackSignatureError(PermissionError):
    """Raised when a request did not come from Slack."""


class SlackAgentError(RuntimeError):
    """Raised when the Slack agent cannot satisfy a request."""


@dataclass
class SlackCommandResult:
    text: str
    title: str | None = None


def verify_slack_signature(
    *,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
    signing_secret: str | None = None,
    now: int | None = None,
) -> None:
    secret = (signing_secret or os.getenv("SLACK_SIGNING_SECRET", "")).strip()
    if not secret:
        raise SlackSignatureError("SLACK_SIGNING_SECRET is not configured.")
    if not timestamp or not signature:
        raise SlackSignatureError("Missing Slack signature headers.")

    try:
        request_age = abs((now or int(time.time())) - int(timestamp))
    except ValueError as exc:
        raise SlackSignatureError("Slack request timestamp is invalid.") from exc

    if request_age > 60 * 5:
        raise SlackSignatureError("Slack request is too old.")

    basestring = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    expected = "v0=" + hmac.new(secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise SlackSignatureError("Slack request signature is invalid.")


def handle_slack_event(payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get("event") or {}
    event_type = str(event.get("type") or "").strip()

    if event_type == "assistant_thread_started":
        _handle_thread_started(event)
    elif event_type == "message.im":
        _handle_user_message(event)
    elif event_type == "app_mention":
        _handle_user_message(event)

    return {"ok": True}


def handle_interactivity(payload: dict[str, Any]) -> dict[str, Any]:
    actions = payload.get("actions") or []
    if not actions:
        return {"ok": True}

    action = actions[0]
    action_id = str(action.get("action_id") or "")
    if action_id not in {"approval_approve", "approval_deny"}:
        return {"ok": True}

    value = str(action.get("value") or "")
    approval_id_text, _, resolution = value.partition(":")
    approval_id = int(approval_id_text)
    slack_user_id = str((payload.get("user") or {}).get("id") or "")
    channel_id = str((payload.get("channel") or {}).get("id") or "")
    message_ts = str((payload.get("message") or {}).get("ts") or "")

    try:
        resolved = resolve_approval(
            approval_id,
            ApprovalResolutionRequest(slack_user_id=slack_user_id, resolution=resolution),
        )
    except PermissionError as exc:
        return {"text": str(exc), "response_type": "ephemeral"}
    except ValueError as exc:
        return {"text": str(exc), "response_type": "ephemeral"}

    approval = get_approval_request(approval_id)
    result_text = _format_resolution_message(resolved.id, resolved.status, slack_user_id, approval)
    if channel_id and message_ts:
        client = SlackApiClient()
        try:
            client.update_message(channel=channel_id, ts=message_ts, text=result_text)
        finally:
            client.close()
    return {"text": result_text, "replace_original": False}


def _handle_thread_started(event: dict[str, Any]) -> None:
    assistant_thread = event.get("assistant_thread") or {}
    channel_id = str(assistant_thread.get("channel_id") or event.get("channel") or "")
    thread_ts = str(assistant_thread.get("thread_ts") or event.get("thread_ts") or "")
    if not channel_id or not thread_ts:
        return

    client = SlackApiClient()
    try:
        client.set_title(channel_id=channel_id, thread_ts=thread_ts, title="Virtual Org")
        client.set_suggested_prompts(
            channel_id=channel_id,
            thread_ts=thread_ts,
            title="Try one of these",
            prompts=[
                {"title": "What is blocked?", "message": "What is blocked right now?"},
                {"title": "Show approvals", "message": "Show pending approvals."},
                {"title": "Daily briefing", "message": "Give me a daily briefing."},
                {"title": "Run one pass", "message": "Run one worker pass."},
            ],
        )
        client.post_message(
            channel=channel_id,
            thread_ts=thread_ts,
            text=(
                "I can check blockers, show approvals, summarise a task, and trigger one safe worker pass. "
                "Try: `what is blocked`, `show approvals`, `task 123`, `daily briefing`, or `run one worker pass`."
            ),
        )
    finally:
        client.close()


def _handle_user_message(event: dict[str, Any]) -> None:
    if event.get("bot_id") or event.get("subtype"):
        return

    channel_id = str(event.get("channel") or "")
    thread_ts = str(event.get("thread_ts") or event.get("ts") or "")
    user_id = str(event.get("user") or "")
    raw_text = str(event.get("text") or "").strip()
    if not channel_id or not thread_ts or not raw_text:
        return

    normalized_text = _normalize_user_text(raw_text)

    client = SlackApiClient()
    try:
        try:
            client.set_status(
                channel_id=channel_id,
                thread_ts=thread_ts,
                status="Checking the control plane",
                loading_messages=["Checking tasks", "Checking approvals", "Summarising the current state"],
            )
        except Exception:
            pass

        result = _run_command(normalized_text, slack_user_id=user_id)
        if result.title:
            try:
                client.set_title(channel_id=channel_id, thread_ts=thread_ts, title=result.title[:80])
            except Exception:
                pass
        client.post_message(channel=channel_id, thread_ts=thread_ts, text=result.text)
    finally:
        client.close()


def _run_command(text: str, *, slack_user_id: str) -> SlackCommandResult:
    if text in {"help", "what can you do", "what can you do?"}:
        return SlackCommandResult(_help_text(), title="Available commands")

    if text in {"show approvals", "approvals", "pending approvals"}:
        return SlackCommandResult(_pending_approvals_text(), title="Pending approvals")

    if text in {"what is blocked", "what is blocked?", "blocked", "show blockers"}:
        return SlackCommandResult(_blocked_items_text(), title="Blocked right now")

    if text in {"daily briefing", "briefing", "give me a daily briefing"}:
        return SlackCommandResult(_briefing_text("daily"), title="Daily briefing")

    if text in {"run one worker pass", "run worker", "run one pass"}:
        return SlackCommandResult(_run_worker_text(), title="Worker pass")

    if text.startswith("task "):
        return SlackCommandResult(_task_state_text(text.removeprefix("task ").strip()), title="Task status")

    if text.startswith("approve "):
        return SlackCommandResult(_resolve_approval_text(text.removeprefix("approve ").strip(), "approved", slack_user_id))

    if text.startswith("deny "):
        return SlackCommandResult(_resolve_approval_text(text.removeprefix("deny ").strip(), "denied", slack_user_id))

    return SlackCommandResult(
        "I did not understand that yet.\n\n" + _help_text(),
        title="Try one of these",
    )


def _help_text() -> str:
    return "\n".join(
        [
            "I can help with the control plane from inside Slack.",
            "",
            "Try one of these:",
            "- `what is blocked`",
            "- `show approvals`",
            "- `task 123`",
            "- `daily briefing`",
            "- `run one worker pass`",
            "- `approve 12`",
            "- `deny 12`",
        ]
    )


def _pending_approvals_text() -> str:
    approvals = get_pending_approvals(limit=10)
    if not approvals:
        return "There are no pending approvals."
    lines = ["Pending approvals:"]
    for approval in approvals:
        lines.append(f"- #{approval.id} task {approval.task_id}: {approval.action_type} -> {approval.target_summary}")
    return "\n".join(lines)


def _blocked_items_text() -> str:
    approvals = get_pending_approvals(limit=5)
    attention_items = list_attention_items(limit=10)

    lines: list[str] = []
    if approvals:
        lines.append("Pending approvals:")
        for approval in approvals:
            lines.append(f"- #{approval.id} task {approval.task_id}: {approval.target_summary}")

    open_alerts = [item for item in attention_items if item.severity.lower() in {"critical", "high"}]
    if open_alerts:
        if lines:
            lines.append("")
        lines.append("High-priority alerts:")
        for item in open_alerts[:5]:
            task_part = f" task {item.task_id}" if item.task_id is not None else ""
            lines.append(f"- {item.severity.upper()}{task_part}: {item.headline}")

    return "\n".join(lines) if lines else "Nothing is blocked right now."


def _briefing_text(scope: str) -> str:
    briefing = generate_briefing(scope=scope, delivered_to="slack-agent")
    lines = [briefing.headline]
    if not briefing.items_json:
        lines.append("No active attention items.")
    else:
        for item in briefing.items_json[:5]:
            lines.append(f"- [{item['severity'].upper()}] {item['headline']} -> {item['recommended_action']}")
    return "\n".join(lines)


def _run_worker_text() -> str:
    result = TaskRunner(worker_id="slack-agent").run_once()
    return result.message


def _task_state_text(task_id_text: str) -> str:
    if not task_id_text.isdigit():
        return "Use `task 123` with a real task number."
    state = get_task_control_state(int(task_id_text))
    if not state:
        return f"Task {task_id_text} was not found."

    task = state["task"]
    lines = [
        f"Task {task.id}: {task.title}",
        f"Status: {task.status}",
        f"Category: {task.category}",
    ]
    if task.branch_name:
        lines.append(f"Branch: {task.branch_name}")
    if task.pr_url:
        lines.append(f"PR: {task.pr_url}")
    approvals = state["approval_requests"]
    if approvals:
        lines.append(f"Approvals: {len([item for item in approvals if item.status == 'pending'])} pending")
    attention = state["attention_items"]
    if attention:
        latest = attention[0]
        lines.append(f"Latest alert: [{latest.severity.upper()}] {latest.headline}")
    return "\n".join(lines)


def _resolve_approval_text(raw: str, resolution: str, slack_user_id: str) -> str:
    approval_id_text = raw.split()[0] if raw.strip() else ""
    if not approval_id_text.isdigit():
        return f"Use `{resolution == 'approved' and 'approve' or 'deny'} 12` with a real approval number."
    try:
        resolved = resolve_approval(
            int(approval_id_text),
            ApprovalResolutionRequest(slack_user_id=slack_user_id, resolution=resolution),
        )
    except PermissionError as exc:
        return str(exc)
    except ValueError as exc:
        return str(exc)
    approval = get_approval_request(int(approval_id_text))
    return _format_resolution_message(resolved.id, resolved.status, slack_user_id, approval)


def _format_resolution_message(
    approval_id: int,
    status: str,
    slack_user_id: str,
    approval: Any | None,
) -> str:
    status_word = "approved" if status == "approved" else "denied"
    suffix = ""
    if approval:
        suffix = f" for task {approval.task_id}: {approval.target_summary}"
    return f"Approval #{approval_id} {status_word} by <@{slack_user_id}>{suffix}."


def _normalize_user_text(text: str) -> str:
    without_mentions = " ".join(part for part in text.split() if not part.startswith("<@"))
    return without_mentions.strip().lower()


def parse_interactivity_payload(raw_payload: str) -> dict[str, Any]:
    try:
        return json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise SlackAgentError("Slack interactivity payload is invalid JSON.") from exc
