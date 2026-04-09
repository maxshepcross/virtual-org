"""Control-plane records for approvals, signals, agent runs, and briefings."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg2.extras
from pydantic import BaseModel, Field

from models.task import _conn, get_task


class AgentRun(BaseModel):
    id: int | None = None
    task_id: int | None = None
    run_key: str | None = None
    parent_run_id: int | None = None
    story_id: str | None = None
    run_kind: str = "interactive"
    trigger_source: str = "manual"
    triggered_by: str | None = None
    approved_by: str | None = None
    completed_by: str | None = None
    agent_class: str
    agent_role: str
    repo_name: str | None = None
    branch_name: str | None = None
    pr_url: str | None = None
    slack_channel_id: str | None = None
    slack_thread_ts: str | None = None
    openclaw_session_id: str | None = None
    status: str = "running"
    artifact_summary_json: list[dict[str, Any]] = Field(default_factory=list)
    context_json: dict[str, Any] | None = None
    tool_bundle_json: list[str] | None = None
    resume_context_json: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_heartbeat_at: datetime | None = None


class Signal(BaseModel):
    id: int | None = None
    source: str
    kind: str
    task_id: int | None = None
    agent_run_id: int | None = None
    venture: str | None = None
    severity: str
    summary: str
    details_json: dict[str, Any] | None = None
    dedupe_key: str
    bucket: str
    status: str = "open"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AttentionItem(BaseModel):
    id: int | None = None
    signal_id: int | None = None
    task_id: int | None = None
    agent_run_id: int | None = None
    venture: str | None = None
    bucket: str
    severity: str
    headline: str
    recommended_action: str
    slack_channel_id: str | None = None
    slack_thread_ts: str | None = None
    slack_message_ts: str | None = None
    slack_posted_at: datetime | None = None
    status: str = "open"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None


class ApprovalRequest(BaseModel):
    id: int | None = None
    task_id: int
    agent_run_id: int | None = None
    action_type: str
    target_summary: str
    status: str = "pending"
    requested_slack_channel_id: str | None = None
    requested_slack_thread_ts: str | None = None
    slack_message_ts: str | None = None
    slack_posted_at: datetime | None = None
    approved_by_slack_user_id: str | None = None
    resolution_note: str | None = None
    external_event_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None


class PolicyDecision(BaseModel):
    id: int | None = None
    agent_run_id: int | None = None
    task_id: int
    story_id: str | None = None
    tool_name: str | None = None
    action_type: str
    target_type: str | None = None
    target_host: str | None = None
    target_repo: str | None = None
    decision: str
    policy_name: str
    reason: str
    approval_request_id: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Briefing(BaseModel):
    id: int | None = None
    scope: str
    headline: str
    items_json: list[dict[str, Any]] = Field(default_factory=list)
    delivered_to: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _decode_json_fields(row: dict[str, Any], *fields: str) -> dict[str, Any]:
    for field in fields:
        if row.get(field) and isinstance(row[field], str):
            row[field] = json.loads(row[field])
    return row


def _row_to_model(row: dict[str, Any] | None, model: type[BaseModel], *json_fields: str) -> BaseModel | None:
    if not row:
        return None
    return model(**_decode_json_fields(row, *json_fields))


def create_agent_run(
    task_id: int | None,
    story_id: str | None,
    agent_class: str,
    agent_role: str,
    *,
    run_key: str | None = None,
    parent_run_id: int | None = None,
    run_kind: str = "interactive",
    trigger_source: str = "manual",
    triggered_by: str | None = None,
    repo_name: str | None = None,
    branch_name: str | None = None,
    slack_channel_id: str | None = None,
    slack_thread_ts: str | None = None,
    openclaw_session_id: str | None = None,
    status: str = "running",
    artifact_summary_json: list[dict[str, Any]] | None = None,
    context_json: dict[str, Any] | None = None,
    tool_bundle_json: list[str] | None = None,
    resume_context_json: dict[str, Any] | None = None,
) -> AgentRun:
    run_key = run_key or str(uuid.uuid4())
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO agent_runs (
                    task_id,
                    run_key,
                    parent_run_id,
                    story_id,
                    run_kind,
                    trigger_source,
                    triggered_by,
                    agent_class,
                    agent_role,
                    repo_name,
                    branch_name,
                    slack_channel_id,
                    slack_thread_ts,
                    openclaw_session_id,
                    status,
                    artifact_summary_json,
                    context_json,
                    tool_bundle_json,
                    resume_context_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    task_id,
                    run_key,
                    parent_run_id,
                    story_id,
                    run_kind,
                    trigger_source,
                    triggered_by,
                    agent_class,
                    agent_role,
                    repo_name,
                    branch_name,
                    slack_channel_id,
                    slack_thread_ts,
                    openclaw_session_id,
                    status,
                    json.dumps(artifact_summary_json or []),
                    json.dumps(context_json) if context_json is not None else None,
                    json.dumps(tool_bundle_json) if tool_bundle_json is not None else None,
                    json.dumps(resume_context_json) if resume_context_json is not None else None,
                ),
            )
            conn.commit()
            return _row_to_model(
                cur.fetchone(),
                AgentRun,
                "artifact_summary_json",
                "context_json",
                "tool_bundle_json",
                "resume_context_json",
            )
    finally:
        conn.close()


def update_agent_run(
    run_id: int,
    status: str | None = None,
    *,
    approved_by: str | None = None,
    completed_by: str | None = None,
    branch_name: str | None = None,
    pr_url: str | None = None,
    slack_channel_id: str | None = None,
    slack_thread_ts: str | None = None,
    context_json: dict[str, Any] | None = None,
    tool_bundle_json: list[str] | None = None,
    resume_context_json: dict[str, Any] | None = None,
    error_message: str | None = None,
    openclaw_session_id: str | None = None,
) -> AgentRun | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            set_parts = ["last_heartbeat_at = NOW()"]
            params: list[Any] = []

            if status is not None:
                set_parts.append("status = %s")
                params.append(status)
            if status in {"completed", "failed", "cancelled", "awaiting_manual_verification"}:
                set_parts.append("finished_at = NOW()")
            if approved_by is not None:
                set_parts.append("approved_by = %s")
                params.append(approved_by)
            if completed_by is not None:
                set_parts.append("completed_by = %s")
                params.append(completed_by)
            if branch_name is not None:
                set_parts.append("branch_name = %s")
                params.append(branch_name)
            if pr_url is not None:
                set_parts.append("pr_url = %s")
                params.append(pr_url)
            if slack_channel_id is not None:
                set_parts.append("slack_channel_id = %s")
                params.append(slack_channel_id)
            if slack_thread_ts is not None:
                set_parts.append("slack_thread_ts = %s")
                params.append(slack_thread_ts)
            if context_json is not None:
                set_parts.append("context_json = %s")
                params.append(json.dumps(context_json))
            if tool_bundle_json is not None:
                set_parts.append("tool_bundle_json = %s")
                params.append(json.dumps(tool_bundle_json))
            if resume_context_json is not None:
                set_parts.append("resume_context_json = %s")
                params.append(json.dumps(resume_context_json))
            if error_message is not None:
                set_parts.append("error_message = %s")
                params.append(error_message)
            if openclaw_session_id is not None:
                set_parts.append("openclaw_session_id = %s")
                params.append(openclaw_session_id)

            params.append(run_id)
            cur.execute(
                f"""
                UPDATE agent_runs
                SET {', '.join(set_parts)}
                WHERE id = %s
                RETURNING *
                """,
                params,
            )
            conn.commit()
            return _row_to_model(
                cur.fetchone(),
                AgentRun,
                "artifact_summary_json",
                "context_json",
                "tool_bundle_json",
                "resume_context_json",
            )
    finally:
        conn.close()


def append_agent_run_artifact(run_id: int, artifact: dict[str, Any]) -> AgentRun | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE agent_runs
                SET artifact_summary_json = COALESCE(artifact_summary_json, '[]'::jsonb) || %s::jsonb,
                    last_heartbeat_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (json.dumps([artifact]), run_id),
            )
            conn.commit()
            return _row_to_model(
                cur.fetchone(),
                AgentRun,
                "artifact_summary_json",
                "context_json",
                "tool_bundle_json",
                "resume_context_json",
            )
    finally:
        conn.close()


def create_signal(
    *,
    source: str,
    kind: str,
    task_id: int | None,
    agent_run_id: int | None,
    venture: str | None,
    severity: str,
    summary: str,
    details_json: dict[str, Any] | None,
    dedupe_key: str,
    bucket: str,
) -> Signal:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO signals (
                    source, kind, task_id, agent_run_id, venture, severity, summary, details_json, dedupe_key, bucket
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    source,
                    kind,
                    task_id,
                    agent_run_id,
                    venture,
                    severity,
                    summary,
                    json.dumps(details_json) if details_json is not None else None,
                    dedupe_key,
                    bucket,
                ),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), Signal, "details_json")
    finally:
        conn.close()


def find_recent_signal_by_dedupe_key(dedupe_key: str, freshness_seconds: int = 300) -> Signal | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM signals
                WHERE dedupe_key = %s
                  AND created_at >= NOW() - (%s || ' seconds')::interval
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (dedupe_key, freshness_seconds),
            )
            return _row_to_model(cur.fetchone(), Signal, "details_json")
    finally:
        conn.close()


def create_attention_item(
    *,
    signal_id: int | None,
    task_id: int | None,
    agent_run_id: int | None,
    venture: str | None,
    bucket: str,
    severity: str,
    headline: str,
    recommended_action: str,
    slack_channel_id: str | None = None,
    slack_thread_ts: str | None = None,
) -> AttentionItem:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO attention_items (
                    signal_id,
                    task_id,
                    agent_run_id,
                    venture,
                    bucket,
                    severity,
                    headline,
                    recommended_action,
                    slack_channel_id,
                    slack_thread_ts
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    signal_id,
                    task_id,
                    agent_run_id,
                    venture,
                    bucket,
                    severity,
                    headline,
                    recommended_action,
                    slack_channel_id,
                    slack_thread_ts,
                ),
            )
            row = cur.fetchone()
            if task_id is not None:
                cur.execute(
                    """
                    UPDATE tasks
                    SET latest_attention_severity = %s,
                        approval_state = CASE
                            WHEN %s = 'approval_required' THEN 'pending'
                            ELSE approval_state
                        END
                    WHERE id = %s
                    """,
                    (severity, bucket, task_id),
                )
            conn.commit()
            return _row_to_model(row, AttentionItem)
    finally:
        conn.close()


def list_attention_items(limit: int = 50, status: str = "open") -> list[AttentionItem]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM attention_items
                WHERE status = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (status, limit),
            )
            return [
                _row_to_model(row, AttentionItem)
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def list_unposted_attention_items(limit: int = 50) -> list[AttentionItem]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM attention_items
                WHERE status = 'open'
                  AND slack_channel_id IS NOT NULL
                  AND slack_posted_at IS NULL
                ORDER BY created_at ASC, id ASC
                LIMIT %s
                """,
                (limit,),
            )
            return [_row_to_model(row, AttentionItem) for row in cur.fetchall()]
    finally:
        conn.close()


def mark_attention_item_posted(attention_item_id: int, *, slack_message_ts: str | None = None) -> AttentionItem | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE attention_items
                SET slack_message_ts = %s,
                    slack_posted_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (slack_message_ts, attention_item_id),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), AttentionItem)
    finally:
        conn.close()


def create_approval_request(
    *,
    task_id: int,
    agent_run_id: int | None,
    action_type: str,
    target_summary: str,
    requested_slack_channel_id: str | None = None,
    requested_slack_thread_ts: str | None = None,
    external_event_id: str | None = None,
) -> ApprovalRequest:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO approval_requests (
                    task_id,
                    agent_run_id,
                    action_type,
                    target_summary,
                    requested_slack_channel_id,
                    requested_slack_thread_ts,
                    external_event_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (external_event_id) WHERE external_event_id IS NOT NULL
                DO NOTHING
                RETURNING *
                """,
                (
                    task_id,
                    agent_run_id,
                    action_type,
                    target_summary,
                    requested_slack_channel_id,
                    requested_slack_thread_ts,
                    external_event_id,
                ),
            )
            row = cur.fetchone()
            if row is None and external_event_id is not None:
                cur.execute(
                    "SELECT * FROM approval_requests WHERE external_event_id = %s",
                    (external_event_id,),
                )
                row = cur.fetchone()

            if row and row["status"] == "pending":
                cur.execute(
                    "UPDATE tasks SET approval_state = 'pending', status = 'awaiting_approval' WHERE id = %s",
                    (task_id,),
                )
            conn.commit()
            return _row_to_model(row, ApprovalRequest)
    finally:
        conn.close()


def get_approval_request(approval_id: int) -> ApprovalRequest | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM approval_requests WHERE id = %s", (approval_id,))
            return _row_to_model(cur.fetchone(), ApprovalRequest)
    finally:
        conn.close()


def list_pending_approvals(limit: int = 50) -> list[ApprovalRequest]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM approval_requests
                WHERE status = 'pending'
                ORDER BY created_at ASC, id ASC
                LIMIT %s
                """,
                (limit,),
            )
            return [_row_to_model(row, ApprovalRequest) for row in cur.fetchall()]
    finally:
        conn.close()


def list_unposted_approval_requests(limit: int = 50) -> list[ApprovalRequest]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM approval_requests
                WHERE status = 'pending'
                  AND requested_slack_channel_id IS NOT NULL
                  AND slack_posted_at IS NULL
                ORDER BY created_at ASC, id ASC
                LIMIT %s
                """,
                (limit,),
            )
            return [_row_to_model(row, ApprovalRequest) for row in cur.fetchall()]
    finally:
        conn.close()


def mark_approval_request_posted(approval_id: int, *, slack_message_ts: str | None = None) -> ApprovalRequest | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE approval_requests
                SET slack_message_ts = %s,
                    slack_posted_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (slack_message_ts, approval_id),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), ApprovalRequest)
    finally:
        conn.close()


def resolve_approval_request(
    approval_id: int,
    *,
    status: str,
    approved_by_slack_user_id: str,
    resolution_note: str | None = None,
) -> ApprovalRequest | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE approval_requests
                SET status = %s,
                    approved_by_slack_user_id = %s,
                    resolution_note = %s,
                    resolved_at = NOW()
                WHERE id = %s AND status = 'pending'
                RETURNING *
                """,
                (status, approved_by_slack_user_id, resolution_note, approval_id),
            )
            row = cur.fetchone()
            if not row:
                cur.execute("SELECT * FROM approval_requests WHERE id = %s", (approval_id,))
                row = cur.fetchone()
                conn.commit()
                return _row_to_model(row, ApprovalRequest) if row else None

            task_id = row["task_id"]
            task_status = "implementing" if status == "approved" else "blocked"
            cur.execute(
                """
                UPDATE tasks
                SET approval_state = %s,
                    status = %s
                WHERE id = %s
                """,
                (status, task_status, task_id),
            )
            conn.commit()
            return _row_to_model(row, ApprovalRequest)
    finally:
        conn.close()


def create_policy_decision(
    *,
    task_id: int,
    action_type: str,
    decision: str,
    policy_name: str,
    reason: str,
    agent_run_id: int | None = None,
    story_id: str | None = None,
    tool_name: str | None = None,
    target_type: str | None = None,
    target_host: str | None = None,
    target_repo: str | None = None,
    approval_request_id: int | None = None,
) -> PolicyDecision:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO policy_decisions (
                    task_id,
                    action_type,
                    decision,
                    policy_name,
                    reason,
                    agent_run_id,
                    story_id,
                    tool_name,
                    target_type,
                    target_host,
                    target_repo,
                    approval_request_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    task_id,
                    action_type,
                    decision,
                    policy_name,
                    reason,
                    agent_run_id,
                    story_id,
                    tool_name,
                    target_type,
                    target_host,
                    target_repo,
                    approval_request_id,
                ),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), PolicyDecision)
    finally:
        conn.close()


def create_briefing(scope: str, headline: str, items_json: list[dict[str, Any]], delivered_to: str | None = None) -> Briefing:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO briefings (scope, headline, items_json, delivered_to)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (scope, headline, json.dumps(items_json), delivered_to),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), Briefing, "items_json")
    finally:
        conn.close()


def get_task_control_state(task_id: int) -> dict[str, Any] | None:
    task = get_task(task_id)
    if not task:
        return None

    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM attention_items
                WHERE task_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 10
                """,
                (task_id,),
            )
            attention = [_row_to_model(row, AttentionItem) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT *
                FROM approval_requests
                WHERE task_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 10
                """,
                (task_id,),
            )
            approvals = [_row_to_model(row, ApprovalRequest) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT *
                FROM policy_decisions
                WHERE task_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 10
                """,
                (task_id,),
            )
            decisions = [_row_to_model(row, PolicyDecision) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT *
                FROM agent_runs
                WHERE task_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 10
                """,
                (task_id,),
            )
            agent_runs = [
                _row_to_model(
                    row,
                    AgentRun,
                    "artifact_summary_json",
                    "context_json",
                    "tool_bundle_json",
                    "resume_context_json",
                )
                for row in cur.fetchall()
            ]
    finally:
        conn.close()

    return {
        "task": task,
        "attention_items": attention,
        "approval_requests": approvals,
        "policy_decisions": decisions,
        "agent_runs": agent_runs,
    }
