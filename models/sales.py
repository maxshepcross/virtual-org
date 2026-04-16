"""Sales agent records for the Tempa outbound experiment.

This module owns database reads and writes for sales agents, prospects,
preview tokens, suppression, sends, and eval records.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras
from pydantic import BaseModel, Field

from models.task import _conn


PROSPECT_STATUSES = {
    "imported",
    "enriched",
    "personalization_pending",
    "personalization_failed",
    "eval_failed",
    "ready_to_preview",
    "ready_to_send",
    "sent",
    "replied",
    "bounced",
    "complained",
    "unsubscribed",
    "suppressed",
    "skipped",
}

PROSPECT_TRANSITIONS: dict[str, set[str]] = {
    "imported": {"enriched", "personalization_pending", "skipped", "suppressed"},
    "enriched": {"personalization_pending", "skipped", "suppressed"},
    "personalization_pending": {"personalization_failed", "eval_failed", "ready_to_preview", "suppressed"},
    "personalization_failed": {"personalization_pending", "skipped"},
    "eval_failed": {"personalization_pending", "skipped"},
    "ready_to_preview": {"ready_to_send", "suppressed", "skipped"},
    "ready_to_send": {"sent", "suppressed", "skipped"},
    "sent": {"replied", "bounced", "complained", "unsubscribed"},
    "replied": {"unsubscribed"},
    "bounced": {"suppressed"},
    "complained": {"suppressed"},
    "unsubscribed": {"suppressed"},
    "suppressed": set(),
    "skipped": set(),
}


class InvalidProspectTransition(ValueError):
    """Raised when a prospect is moved through an unsafe state transition."""


class SalesAgent(BaseModel):
    id: int | None = None
    venture: str = "tempa"
    name: str
    status: str = "paused"
    send_mode: str = "dry_run"
    daily_new_prospect_limit: int = 5
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


class SalesSenderAccount(BaseModel):
    id: int | None = None
    agent_id: int
    email: str
    inbox_id: str
    status: str = "paused"
    daily_cap: int = 5
    verified: bool = False
    pause_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


class SalesProspect(BaseModel):
    id: int | None = None
    agent_id: int
    source: str
    external_id: str | None = None
    email: str
    normalized_email_hash: str
    first_name: str | None = None
    last_name: str | None = None
    title: str | None = None
    company_name: str
    company_domain: str | None = None
    company_url: str | None = None
    country: str | None = None
    status: str = "imported"
    source_context_json: dict[str, Any] = Field(default_factory=dict)
    events_json: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


class SalesPersonalization(BaseModel):
    id: int | None = None
    prospect_id: int
    strategy_json: dict[str, Any]
    email_subject: str
    email_body: str
    status: str = "drafted"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SalesOutreachMessage(BaseModel):
    id: int | None = None
    agent_id: int
    prospect_id: int
    sender_account_id: int | None = None
    personalization_id: int | None = None
    preview_token_id: int | None = None
    subject: str
    body: str
    status: str = "drafted"
    agentmail_message_id: str | None = None
    sent_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


class SalesPreviewToken(BaseModel):
    id: int | None = None
    prospect_id: int
    token_hash: str
    purpose: str
    status: str = "valid"
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    revoked_at: datetime | None = None


class SalesSuppressionEntry(BaseModel):
    id: int | None = None
    normalized_email_hash: str | None = None
    domain: str | None = None
    reason: str
    source: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SalesSendEvent(BaseModel):
    id: int | None = None
    event_id: str
    event_type: str
    agentmail_message_id: str | None = None
    prospect_id: int | None = None
    sender_account_id: int | None = None
    safe_metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SalesReplyTriageEvent(BaseModel):
    id: int | None = None
    send_event_id: int | None = None
    prospect_id: int | None = None
    classification: str
    suggested_response_angle: str | None = None
    model_output_json: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SalesEvalResult(BaseModel):
    id: int | None = None
    prospect_id: int
    personalization_id: int | None = None
    status: str
    deterministic_passed: bool
    llm_passed: bool | None = None
    failures_json: list[str] = Field(default_factory=list)
    rubric_json: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_email(email: str) -> str:
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_public_token() -> str:
    return secrets.token_urlsafe(32)


def redact_email(email: str) -> str:
    normalized = normalize_email(email)
    if "@" not in normalized:
        return "[invalid-email]"
    local, domain = normalized.split("@", 1)
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}***@{domain}"


def _decode_json_fields(row: dict[str, Any], *fields: str) -> dict[str, Any]:
    for field in fields:
        if row.get(field) and isinstance(row[field], str):
            row[field] = json.loads(row[field])
    return row


def _row_to_model(row: dict[str, Any] | None, model: type[BaseModel], *json_fields: str):
    if not row:
        return None
    return model(**_decode_json_fields(row, *json_fields))


def _event(event_type: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": event_type,
        "at": datetime.now(timezone.utc).isoformat(),
        "message": message,
        "details": details or {},
    }


def create_sales_agent(
    *,
    name: str,
    venture: str = "tempa",
    status: str = "paused",
    send_mode: str = "dry_run",
    daily_new_prospect_limit: int = 5,
) -> SalesAgent:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO sales_agents (venture, name, status, send_mode, daily_new_prospect_limit)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (venture, name, status, send_mode, daily_new_prospect_limit),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesAgent)
    finally:
        conn.close()


def get_sales_agent(agent_id: int) -> SalesAgent | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM sales_agents WHERE id = %s", (agent_id,))
            return _row_to_model(cur.fetchone(), SalesAgent)
    finally:
        conn.close()


def list_sales_agents(*, limit: int = 50, venture: str | None = None) -> list[SalesAgent]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if venture:
                cur.execute("SELECT * FROM sales_agents WHERE venture = %s ORDER BY id DESC LIMIT %s", (venture, limit))
            else:
                cur.execute("SELECT * FROM sales_agents ORDER BY id DESC LIMIT %s", (limit,))
            return [_row_to_model(row, SalesAgent) for row in cur.fetchall()]
    finally:
        conn.close()


def set_sales_agent_status(agent_id: int, status: str) -> SalesAgent | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE sales_agents
                SET status = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (status, agent_id),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesAgent)
    finally:
        conn.close()


def set_sales_agent_send_mode(agent_id: int, send_mode: str) -> SalesAgent | None:
    if send_mode not in {"dry_run", "live"}:
        raise ValueError("Sales agent send_mode must be 'dry_run' or 'live'.")
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE sales_agents
                SET send_mode = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (send_mode, agent_id),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesAgent)
    finally:
        conn.close()


def create_sender_account(
    *,
    agent_id: int,
    email: str,
    inbox_id: str,
    status: str = "paused",
    daily_cap: int = 5,
    verified: bool = False,
) -> SalesSenderAccount:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO sales_sender_accounts (agent_id, email, inbox_id, status, daily_cap, verified)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (agent_id, normalize_email(email), inbox_id, status, daily_cap, verified),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesSenderAccount)
    finally:
        conn.close()


def list_sender_accounts(agent_id: int, *, status: str | None = None) -> list[SalesSenderAccount]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if status:
                cur.execute(
                    """
                    SELECT * FROM sales_sender_accounts
                    WHERE agent_id = %s AND status = %s
                    ORDER BY id ASC
                    """,
                    (agent_id, status),
                )
            else:
                cur.execute(
                    "SELECT * FROM sales_sender_accounts WHERE agent_id = %s ORDER BY id ASC",
                    (agent_id,),
                )
            return [_row_to_model(row, SalesSenderAccount) for row in cur.fetchall()]
    finally:
        conn.close()


def pause_sender_account(sender_account_id: int, reason: str) -> SalesSenderAccount | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE sales_sender_accounts
                SET status = 'paused', pause_reason = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (reason, sender_account_id),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesSenderAccount)
    finally:
        conn.close()


def create_prospect(
    *,
    agent_id: int,
    source: str,
    email: str,
    company_name: str,
    external_id: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    title: str | None = None,
    company_domain: str | None = None,
    company_url: str | None = None,
    country: str | None = None,
    source_context_json: dict[str, Any] | None = None,
) -> SalesProspect | None:
    conn = _conn()
    normalized_hash = hash_email(email)
    events = [_event("imported", "Prospect imported.", {"source": source})]
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO sales_prospects (
                    agent_id, source, external_id, email, normalized_email_hash,
                    first_name, last_name, title, company_name, company_domain,
                    company_url, country, source_context_json, events_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (normalized_email_hash) DO NOTHING
                RETURNING *
                """,
                (
                    agent_id,
                    source,
                    external_id,
                    normalize_email(email),
                    normalized_hash,
                    first_name,
                    last_name,
                    title,
                    company_name,
                    company_domain,
                    company_url,
                    country,
                    json.dumps(source_context_json or {}),
                    json.dumps(events),
                ),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesProspect, "source_context_json", "events_json")
    finally:
        conn.close()


def get_prospect(prospect_id: int) -> SalesProspect | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM sales_prospects WHERE id = %s", (prospect_id,))
            return _row_to_model(cur.fetchone(), SalesProspect, "source_context_json", "events_json")
    finally:
        conn.close()


def list_sales_prospects(
    *,
    limit: int = 50,
    agent_id: int | None = None,
    status: str | None = None,
) -> list[SalesProspect]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            where_parts: list[str] = []
            params: list[Any] = []
            if agent_id is not None:
                where_parts.append("agent_id = %s")
                params.append(agent_id)
            if status:
                where_parts.append("status = %s")
                params.append(status)
            where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
            params.append(limit)
            cur.execute(
                f"SELECT * FROM sales_prospects {where_sql} ORDER BY id DESC LIMIT %s",
                params,
            )
            return [_row_to_model(row, SalesProspect, "source_context_json", "events_json") for row in cur.fetchall()]
    finally:
        conn.close()


def transition_prospect_status(
    prospect_id: int,
    new_status: str,
    *,
    event_message: str,
    event_details: dict[str, Any] | None = None,
) -> SalesProspect:
    if new_status not in PROSPECT_STATUSES:
        raise InvalidProspectTransition(f"Unknown prospect status: {new_status}")

    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT status FROM sales_prospects WHERE id = %s FOR UPDATE", (prospect_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Prospect {prospect_id} was not found.")
            old_status = row["status"]
            if new_status not in PROSPECT_TRANSITIONS.get(old_status, set()):
                event = _event(
                    "invalid_transition",
                    f"Invalid transition from {old_status} to {new_status}.",
                    event_details,
                )
                cur.execute(
                    """
                    UPDATE sales_prospects
                    SET events_json = events_json || %s::jsonb, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (json.dumps(event), prospect_id),
                )
                conn.commit()
                raise InvalidProspectTransition(f"Cannot move prospect from {old_status} to {new_status}.")

            event = _event(new_status, event_message, event_details)
            cur.execute(
                """
                UPDATE sales_prospects
                SET status = %s, events_json = events_json || %s::jsonb, updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (new_status, json.dumps(event), prospect_id),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesProspect, "source_context_json", "events_json")
    finally:
        conn.close()


def create_personalization(
    *,
    prospect_id: int,
    strategy_json: dict[str, Any],
    email_subject: str,
    email_body: str,
    status: str = "drafted",
) -> SalesPersonalization:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO sales_personalizations (
                    prospect_id, strategy_json, email_subject, email_body, status
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (prospect_id, json.dumps(strategy_json), email_subject, email_body, status),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesPersonalization, "strategy_json")
    finally:
        conn.close()


def get_personalization(personalization_id: int) -> SalesPersonalization | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM sales_personalizations WHERE id = %s", (personalization_id,))
            return _row_to_model(cur.fetchone(), SalesPersonalization, "strategy_json")
    finally:
        conn.close()


def get_latest_personalization_for_prospect(prospect_id: int) -> SalesPersonalization | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM sales_personalizations
                WHERE prospect_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (prospect_id,),
            )
            return _row_to_model(cur.fetchone(), SalesPersonalization, "strategy_json")
    finally:
        conn.close()


def create_outreach_message(
    *,
    agent_id: int,
    prospect_id: int,
    subject: str,
    body: str,
    sender_account_id: int | None = None,
    personalization_id: int | None = None,
    preview_token_id: int | None = None,
    status: str = "drafted",
) -> SalesOutreachMessage:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO sales_outreach_messages (
                    agent_id, prospect_id, sender_account_id, personalization_id,
                    preview_token_id, subject, body, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (agent_id, prospect_id, sender_account_id, personalization_id, preview_token_id, subject, body, status),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesOutreachMessage)
    finally:
        conn.close()


def list_sales_messages(
    *,
    limit: int = 50,
    agent_id: int | None = None,
    status: str | None = None,
) -> list[SalesOutreachMessage]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            where_parts: list[str] = []
            params: list[Any] = []
            if agent_id is not None:
                where_parts.append("agent_id = %s")
                params.append(agent_id)
            if status:
                where_parts.append("status = %s")
                params.append(status)
            where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
            params.append(limit)
            cur.execute(
                f"SELECT * FROM sales_outreach_messages {where_sql} ORDER BY id DESC LIMIT %s",
                params,
            )
            return [_row_to_model(row, SalesOutreachMessage) for row in cur.fetchall()]
    finally:
        conn.close()


def claim_next_ready_message(
    *,
    agent_id: int,
    sender_account_id: int,
    sender_daily_cap: int,
) -> SalesOutreachMessage | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
	                WITH locked_sender AS (
	                    SELECT id
	                    FROM sales_sender_accounts
	                    WHERE id = %s AND agent_id = %s AND status = 'active'
	                    FOR UPDATE
	                ),
                capacity AS (
                    SELECT 1
                    FROM locked_sender
                    WHERE (
                        SELECT COUNT(*)
                        FROM sales_outreach_messages
                        WHERE sender_account_id = %s
                          AND (
                              sent_at >= date_trunc('day', NOW())
                              OR status = 'sending'
                          )
                    ) < %s
                ),
                candidate AS (
                    SELECT id
                    FROM sales_outreach_messages
                    WHERE agent_id = %s
                      AND status = 'ready_to_send'
                      AND EXISTS (SELECT 1 FROM capacity)
                    ORDER BY id ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE sales_outreach_messages
                SET status = 'sending',
                    sender_account_id = %s,
                    updated_at = NOW()
                WHERE id = (SELECT id FROM candidate)
                RETURNING *
                """,
                (sender_account_id, agent_id, sender_account_id, sender_daily_cap, agent_id, sender_account_id),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesOutreachMessage)
    finally:
        conn.close()


def get_message_by_agentmail_message_id(agentmail_message_id: str) -> SalesOutreachMessage | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM sales_outreach_messages WHERE agentmail_message_id = %s",
                (agentmail_message_id,),
            )
            return _row_to_model(cur.fetchone(), SalesOutreachMessage)
    finally:
        conn.close()


def update_message_status(message_id: int, status: str) -> SalesOutreachMessage | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE sales_outreach_messages
                SET status = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (status, message_id),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesOutreachMessage)
    finally:
        conn.close()


def mark_message_sent(message_id: int, agentmail_message_id: str, sender_account_id: int) -> SalesOutreachMessage | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE sales_outreach_messages
                SET status = 'sent',
                    agentmail_message_id = %s,
                    sender_account_id = %s,
                    sent_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s AND status = 'sending'
                RETURNING *
                """,
                (agentmail_message_id, sender_account_id, message_id),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesOutreachMessage)
    finally:
        conn.close()


def release_claimed_message(message_id: int, *, clear_sender: bool = False) -> SalesOutreachMessage | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE sales_outreach_messages
                SET status = 'ready_to_send',
                    sender_account_id = CASE WHEN %s THEN NULL ELSE sender_account_id END,
                    updated_at = NOW()
                WHERE id = %s AND status = 'sending'
                RETURNING *
                """,
                (clear_sender, message_id),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesOutreachMessage)
    finally:
        conn.close()


def mark_claimed_message_status(message_id: int, status: str) -> SalesOutreachMessage | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE sales_outreach_messages
                SET status = %s, updated_at = NOW()
                WHERE id = %s AND status = 'sending'
                RETURNING *
                """,
                (status, message_id),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesOutreachMessage)
    finally:
        conn.close()


def mark_unsent_messages_for_prospect_status(prospect_id: int, status: str) -> int:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sales_outreach_messages
                SET status = %s, updated_at = NOW()
                WHERE prospect_id = %s
                  AND status IN ('drafted', 'ready_to_send', 'sending')
                """,
                (status, prospect_id),
            )
            updated = cur.rowcount
            conn.commit()
            return updated
    finally:
        conn.close()


def create_preview_token(
    *,
    prospect_id: int,
    purpose: str,
    expires_at: datetime | None,
) -> tuple[str, SalesPreviewToken]:
    raw_token = new_public_token()
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO sales_preview_tokens (prospect_id, token_hash, purpose, expires_at)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (prospect_id, hash_token(raw_token), purpose, expires_at),
            )
            conn.commit()
            return raw_token, _row_to_model(cur.fetchone(), SalesPreviewToken)
    finally:
        conn.close()


def get_preview_token(raw_token: str, *, purpose: str | None = None) -> SalesPreviewToken | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if purpose:
                cur.execute(
                    "SELECT * FROM sales_preview_tokens WHERE token_hash = %s AND purpose = %s",
                    (hash_token(raw_token), purpose),
                )
            else:
                cur.execute("SELECT * FROM sales_preview_tokens WHERE token_hash = %s", (hash_token(raw_token),))
            return _row_to_model(cur.fetchone(), SalesPreviewToken)
    finally:
        conn.close()


def revoke_preview_token(token_id: int) -> SalesPreviewToken | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE sales_preview_tokens
                SET status = 'revoked', revoked_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (token_id,),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesPreviewToken)
    finally:
        conn.close()


def record_suppression(
    *,
    email: str | None = None,
    domain: str | None = None,
    reason: str,
    source: str,
) -> SalesSuppressionEntry:
    if not email and not domain:
        raise ValueError("Suppression requires an email or domain.")
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO sales_suppression_entries (normalized_email_hash, domain, reason, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING *
                """,
                (hash_email(email) if email else None, domain.strip().lower() if domain else None, reason, source),
            )
            conn.commit()
            row = cur.fetchone()
            if row:
                return _row_to_model(row, SalesSuppressionEntry)
            if email:
                cur.execute(
                    "SELECT * FROM sales_suppression_entries WHERE normalized_email_hash = %s LIMIT 1",
                    (hash_email(email),),
                )
            else:
                cur.execute(
                    "SELECT * FROM sales_suppression_entries WHERE domain = %s LIMIT 1",
                    (domain.strip().lower(),),
                )
            return _row_to_model(cur.fetchone(), SalesSuppressionEntry)
    finally:
        conn.close()


def is_suppressed(*, email: str, domain: str | None = None) -> bool:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM sales_suppression_entries
                WHERE normalized_email_hash = %s
                   OR (%s IS NOT NULL AND domain = %s)
                LIMIT 1
                """,
                (hash_email(email), domain.strip().lower() if domain else None, domain.strip().lower() if domain else None),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def record_send_event(
    *,
    event_id: str,
    event_type: str,
    agentmail_message_id: str | None = None,
    prospect_id: int | None = None,
    sender_account_id: int | None = None,
    safe_metadata_json: dict[str, Any] | None = None,
) -> SalesSendEvent | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO sales_send_events (
                    event_id, event_type, agentmail_message_id, prospect_id,
                    sender_account_id, safe_metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                RETURNING *
                """,
                (
                    event_id,
                    event_type,
                    agentmail_message_id,
                    prospect_id,
                    sender_account_id,
                    json.dumps(safe_metadata_json or {}),
                ),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesSendEvent, "safe_metadata_json")
    finally:
        conn.close()


def record_reply_triage_event(
    *,
    send_event_id: int | None,
    prospect_id: int | None,
    classification: str,
    suggested_response_angle: str | None,
    model_output_json: dict[str, Any] | None = None,
) -> SalesReplyTriageEvent:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO sales_reply_triage_events (
                    send_event_id, prospect_id, classification,
                    suggested_response_angle, model_output_json
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    send_event_id,
                    prospect_id,
                    classification,
                    suggested_response_angle,
                    json.dumps(model_output_json) if model_output_json is not None else None,
                ),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesReplyTriageEvent, "model_output_json")
    finally:
        conn.close()


def record_eval_result(
    *,
    prospect_id: int,
    personalization_id: int | None,
    status: str,
    deterministic_passed: bool,
    llm_passed: bool | None,
    failures_json: list[str],
    rubric_json: dict[str, Any] | None = None,
) -> SalesEvalResult:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO sales_eval_results (
                    prospect_id, personalization_id, status, deterministic_passed,
                    llm_passed, failures_json, rubric_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    prospect_id,
                    personalization_id,
                    status,
                    deterministic_passed,
                    llm_passed,
                    json.dumps(failures_json),
                    json.dumps(rubric_json) if rubric_json is not None else None,
                ),
            )
            conn.commit()
            return _row_to_model(cur.fetchone(), SalesEvalResult, "failures_json", "rubric_json")
    finally:
        conn.close()


def get_latest_eval_result(
    *,
    prospect_id: int | None = None,
    personalization_id: int | None = None,
) -> SalesEvalResult | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            where_parts: list[str] = []
            params: list[Any] = []
            if prospect_id is not None:
                where_parts.append("prospect_id = %s")
                params.append(prospect_id)
            if personalization_id is not None:
                where_parts.append("personalization_id = %s")
                params.append(personalization_id)
            if not where_parts:
                raise ValueError("Eval lookup requires prospect_id or personalization_id.")
            where_sql = " AND ".join(where_parts)
            cur.execute(
                f"""
                SELECT *
                FROM sales_eval_results
                WHERE {where_sql}
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                params,
            )
            return _row_to_model(cur.fetchone(), SalesEvalResult, "failures_json", "rubric_json")
    finally:
        conn.close()


def count_sender_sent_today(sender_account_id: int) -> int:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM sales_outreach_messages
                WHERE sender_account_id = %s
                  AND sent_at >= date_trunc('day', NOW())
                """,
                (sender_account_id,),
            )
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def count_sender_sent_since(sender_account_id: int, *, days: int) -> int:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM sales_outreach_messages
                WHERE sender_account_id = %s
                  AND sent_at >= NOW() - (%s || ' days')::interval
                """,
                (sender_account_id, days),
            )
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def count_sender_events_since(sender_account_id: int, *, event_type: str, days: int) -> int:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM sales_send_events
                WHERE sender_account_id = %s
                  AND event_type = %s
                  AND created_at >= NOW() - (%s || ' days')::interval
                """,
                (sender_account_id, event_type, days),
            )
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def latest_sender_event_at(sender_account_id: int) -> datetime | None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(created_at)
                FROM sales_send_events
                WHERE sender_account_id = %s
                """,
                (sender_account_id,),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


def latest_sender_webhook_event_at(sender_account_id: int) -> datetime | None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(created_at)
                FROM sales_send_events
                WHERE sender_account_id = %s
                  AND event_type NOT IN ('message.sent', 'message.dry_run')
                """,
                (sender_account_id,),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


def latest_sender_sent_at(sender_account_id: int) -> datetime | None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(sent_at)
                FROM sales_outreach_messages
                WHERE sender_account_id = %s
                """,
                (sender_account_id,),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()
