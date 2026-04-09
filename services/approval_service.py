"""Approval flow helpers for Slack-gated actions."""

from __future__ import annotations

import os

from pydantic import BaseModel

from models.control_plane import (
    ApprovalRequest,
    append_agent_run_artifact,
    create_approval_request,
    get_approval_request,
    list_pending_approvals,
    resolve_approval_request,
    update_agent_run,
)
from models.task import get_task
from services.slack_routing import resolve_slack_route


class ApprovalCreateRequest(BaseModel):
    task_id: int
    agent_run_id: int | None = None
    action_type: str
    target_summary: str
    requested_slack_channel_id: str | None = None
    requested_slack_thread_ts: str | None = None
    external_event_id: str | None = None


class ApprovalResolutionRequest(BaseModel):
    slack_user_id: str
    resolution: str
    note: str | None = None


def _trusted_approvers() -> set[str]:
    return {
        user_id.strip()
        for user_id in os.getenv("SLACK_APPROVER_IDS", "").split(",")
        if user_id.strip()
    }


def create_approval(request: ApprovalCreateRequest) -> ApprovalRequest:
    task = get_task(request.task_id)
    if not task:
        raise ValueError(f"Task {request.task_id} was not found.")

    slack_channel_id, slack_thread_ts = resolve_slack_route(
        task_id=request.task_id,
        explicit_channel_id=request.requested_slack_channel_id,
        explicit_thread_ts=request.requested_slack_thread_ts,
    )
    payload = request.model_dump()
    payload["requested_slack_channel_id"] = slack_channel_id
    payload["requested_slack_thread_ts"] = slack_thread_ts
    approval = create_approval_request(**payload)
    if not approval:
        raise ValueError("Approval request could not be created.")
    return approval


def get_pending_approvals(limit: int = 50) -> list[ApprovalRequest]:
    return list_pending_approvals(limit=limit)


def resolve_approval(approval_id: int, request: ApprovalResolutionRequest) -> ApprovalRequest:
    approval = get_approval_request(approval_id)
    if not approval:
        raise ValueError(f"Approval request {approval_id} was not found.")

    if approval.status != "pending":
        return approval

    trusted = _trusted_approvers()
    allow_any_slack_user = "*" in trusted
    if trusted and not allow_any_slack_user and request.slack_user_id not in trusted:
        raise PermissionError("Slack user is not allowed to approve actions.")

    normalized_resolution = request.resolution.strip().lower()
    if normalized_resolution not in {"approved", "denied"}:
        raise ValueError("Resolution must be 'approved' or 'denied'.")

    resolved = resolve_approval_request(
        approval_id,
        status=normalized_resolution,
        approved_by_slack_user_id=request.slack_user_id,
        resolution_note=request.note,
    )
    if not resolved:
        raise ValueError(f"Approval request {approval_id} could not be resolved.")
    if resolved.agent_run_id is not None:
        update_agent_run(
            resolved.agent_run_id,
            approved_by=request.slack_user_id,
        )
        append_agent_run_artifact(
            resolved.agent_run_id,
            {
                "type": "approval_resolution",
                "approval_id": resolved.id,
                "status": normalized_resolution,
                "approved_by": request.slack_user_id,
                "note": request.note or "",
                "at": resolved.resolved_at.isoformat() if resolved.resolved_at else None,
            },
        )
    if resolved.status != normalized_resolution and resolved.status != "pending":
        return resolved
    return resolved
