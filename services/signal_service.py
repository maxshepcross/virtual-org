"""Signal routing logic that decides what reaches the founder attention queue."""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel

from models.control_plane import (
    AttentionItem,
    Signal,
    create_attention_item,
    create_signal,
    find_recent_signal_by_dedupe_key,
)
from services.slack_routing import resolve_slack_route


class SignalInput(BaseModel):
    source: str
    kind: str
    task_id: int | None = None
    agent_run_id: int | None = None
    venture: str | None = None
    severity: str
    summary: str
    details_json: dict[str, Any] | None = None
    dedupe_key: str | None = None
    recommended_action: str | None = None
    slack_channel_id: str | None = None
    slack_thread_ts: str | None = None


def build_dedupe_key(signal: SignalInput) -> str:
    raw = "|".join(
        [
            signal.source.strip().lower(),
            signal.kind.strip().lower(),
            str(signal.task_id or ""),
            signal.summary.strip().lower(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def classify_signal(kind: str, severity: str) -> str:
    normalized_kind = kind.strip().lower()
    normalized_severity = severity.strip().lower()

    if normalized_kind in {"approval_required", "approval_requested"}:
        return "approval_required"
    if normalized_kind in {"heartbeat", "lease_heartbeat"}:
        return "ignore"
    if normalized_kind in {"policy_blocked", "task_failed"}:
        return "notify"
    if normalized_severity in {"critical", "high"}:
        return "notify"
    if normalized_severity == "normal":
        return "digest"
    return "ignore"


def _default_recommended_action(bucket: str, summary: str) -> str:
    if bucket == "approval_required":
        return "Review and approve or deny this request in Slack."
    if bucket == "notify":
        return "Review the issue and decide whether to intervene."
    if bucket == "digest":
        return "Include this in the next summary."
    return f"No action needed for: {summary}"


def record_signal(signal_input: SignalInput) -> dict[str, Signal | AttentionItem | None]:
    dedupe_key = signal_input.dedupe_key or build_dedupe_key(signal_input)
    existing = find_recent_signal_by_dedupe_key(dedupe_key)
    if existing:
        return {"signal": existing, "attention_item": None, "deduped": True}

    bucket = classify_signal(signal_input.kind, signal_input.severity)
    signal = create_signal(
        source=signal_input.source,
        kind=signal_input.kind,
        task_id=signal_input.task_id,
        agent_run_id=signal_input.agent_run_id,
        venture=signal_input.venture,
        severity=signal_input.severity,
        summary=signal_input.summary,
        details_json=signal_input.details_json,
        dedupe_key=dedupe_key,
        bucket=bucket,
    )

    attention_item = None
    if bucket in {"notify", "approval_required"}:
        slack_channel_id, slack_thread_ts = resolve_slack_route(
            task_id=signal.task_id,
            explicit_channel_id=signal_input.slack_channel_id,
            explicit_thread_ts=signal_input.slack_thread_ts,
        )
        attention_item = create_attention_item(
            signal_id=signal.id,
            task_id=signal.task_id,
            agent_run_id=signal.agent_run_id,
            venture=signal.venture,
            bucket=bucket,
            severity=signal.severity,
            headline=signal.summary,
            recommended_action=signal_input.recommended_action
            or _default_recommended_action(bucket, signal.summary),
            slack_channel_id=slack_channel_id,
            slack_thread_ts=slack_thread_ts,
        )

    return {"signal": signal, "attention_item": attention_item, "deduped": False}
