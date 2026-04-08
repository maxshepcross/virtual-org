"""Approval flow helpers for Slack-gated actions."""

from __future__ import annotations

import os

from pydantic import BaseModel

from models.control_plane import (
    ApprovalRequest,
    create_approval_request,
    get_approval_request,
    list_pending_approvals,
    resolve_approval_request,
)


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
    approval = create_approval_request(**request.model_dump())
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
    if trusted and request.slack_user_id not in trusted:
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
    if resolved.status != normalized_resolution and resolved.status != "pending":
        return resolved
    return resolved
