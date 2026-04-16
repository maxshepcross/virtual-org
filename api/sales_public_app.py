"""Public sales app for preview, unsubscribe, and AgentMail webhook routes."""

from __future__ import annotations

import logging
import os
from typing import Any
from html import escape

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from models.sales import (
    InvalidProspectTransition,
    get_message_by_agentmail_message_id,
    get_prospect,
    mark_unsent_messages_for_prospect_status,
    pause_sender_account,
    record_reply_triage_event,
    record_send_event,
    record_suppression,
    transition_prospect_status,
    update_message_status,
)
from services.agentmail_service import AgentMailService
from services.sales_preview_service import SalesPreviewService
from services.sales_reply_triage import SalesReplyTriage
from services.signal_service import SignalInput, record_signal


logger = logging.getLogger(__name__)

app = FastAPI(title="Tempa Sales Public API", version="0.1.0")
_preview_service = SalesPreviewService()
_triage = SalesReplyTriage()


NOINDEX_HEADERS = {
    "X-Robots-Tag": "noindex, nofollow",
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}
MAX_WEBHOOK_BODY_BYTES = int(os.getenv("SALES_WEBHOOK_MAX_BODY_BYTES", "262144") or "262144")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/sales/preview/{token}", response_class=HTMLResponse)
def preview_endpoint(token: str) -> HTMLResponse:
    _, html = _preview_service.resolve_preview(token)
    return HTMLResponse(content=html, headers=NOINDEX_HEADERS)


@app.get("/v1/sales/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe_form_endpoint(token: str) -> HTMLResponse:
    safe_token = escape(token, quote=True)
    html = f"""
    <!doctype html>
    <html lang="en">
    <head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><title>Unsubscribe</title></head>
    <body>
      <main>
        <h1>Unsubscribe</h1>
        <form method="post" action="/v1/sales/unsubscribe/{safe_token}">
          <button type="submit">Unsubscribe</button>
        </form>
      </main>
    </body>
    </html>
    """
    return HTMLResponse(content=html, headers=NOINDEX_HEADERS)


@app.post("/v1/sales/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe_endpoint(token: str) -> HTMLResponse:
    if not _preview_service.unsubscribe(token):
        return HTMLResponse(
            content="<!doctype html><html><body><h1>Unsubscribe link not found</h1></body></html>",
            headers=NOINDEX_HEADERS,
            status_code=404,
        )
    return HTMLResponse(
        content="<!doctype html><html><body><h1>You have been unsubscribed</h1></body></html>",
        headers=NOINDEX_HEADERS,
    )


@app.post("/v1/sales/webhooks/agentmail")
async def agentmail_webhook_endpoint(request: Request) -> JSONResponse:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_WEBHOOK_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Webhook payload is too large.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid content-length header.")
    body = await _read_limited_body(request)
    try:
        payload = AgentMailService().verify_webhook(body, dict(request.headers))
    except PermissionError as exc:
        logger.info("sales_webhook_rejected", extra={"reason": "invalid_signature"})
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.info("sales_webhook_unavailable", extra={"reason": "verification_runtime_error"})
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    event = _safe_event_payload(payload)
    logger.info("sales_webhook_received", extra={"event_type": event["event_type"], "has_message_id": bool(event.get("agentmail_message_id"))})
    recorded = record_send_event(**event)
    if not recorded:
        logger.info("sales_webhook_deduped", extra={"event_type": event["event_type"]})
        return JSONResponse({"status": "deduped"})

    event_type = event["event_type"]
    prospect_id = event.get("prospect_id")
    sender_account_id = event.get("sender_account_id")
    if event_type == "message.delivered":
        _mark_message_status(event.get("agentmail_message_id"), "delivered")
    if event_type == "message.bounced":
        _transition_prospect(prospect_id, "bounced", "AgentMail bounce event received.")
        _suppress_bounced_recipients(payload)
    if event_type == "message.complained":
        if sender_account_id:
            pause_sender_account(sender_account_id, "Spam complaint received.")
        _transition_prospect(prospect_id, "complained", "Spam complaint received.")
        _alert_founder("high", "Sales sender paused after spam complaint.", "Review the sender and prospect immediately.")
    if event_type == "message.rejected":
        if sender_account_id:
            pause_sender_account(sender_account_id, "AgentMail rejected a send.")
        _mark_message_status(event.get("agentmail_message_id"), "rejected")
        _alert_founder("high", "Sales sender paused after AgentMail rejected a send.", "Check sender setup and domain health.")
    if event_type == "message.received":
        triage = _triage.classify(_extract_reply_text(payload))
        record_reply_triage_event(
            send_event_id=recorded.id,
            prospect_id=prospect_id,
            classification=triage.classification,
            suggested_response_angle=triage.suggested_response_angle,
            model_output_json=triage.model_output_json,
        )
        if triage.classification == "unsubscribe":
            _handle_unsubscribe_reply(prospect_id)
        else:
            _transition_prospect(prospect_id, "replied", "Reply received and triaged.")
        if triage.classification == "angry":
            if sender_account_id:
                pause_sender_account(sender_account_id, "Angry reply received.")
            _suppress_prospect_email(prospect_id, "angry_reply")
        _alert_for_reply_triage(triage.classification, triage.suggested_response_angle)
        logger.info(
            "sales_reply_triaged",
            extra={"event_type": event_type, "classification": triage.classification, "prospect_id": prospect_id},
        )
        return JSONResponse({"status": "recorded", "classification": triage.classification})
    logger.info("sales_webhook_recorded", extra={"event_type": event_type, "prospect_id": prospect_id})
    return JSONResponse({"status": "recorded"})


async def _read_limited_body(request: Request) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_WEBHOOK_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Webhook payload is too large.")
        chunks.append(chunk)
    return b"".join(chunks)


def _safe_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    event_type = str(payload.get("event_type") or "unknown")
    event_id = str(payload.get("event_id") or payload.get("id") or "")
    if not event_id:
        raise HTTPException(status_code=400, detail="Webhook event_id is required.")

    message_id = None
    for key in ("send", "delivery", "bounce", "complaint", "reject", "message"):
        section = payload.get(key)
        if isinstance(section, dict) and section.get("message_id"):
            message_id = section.get("message_id")
            break
    message = get_message_by_agentmail_message_id(message_id) if message_id else None
    return {
        "event_id": event_id,
        "event_type": event_type,
        "agentmail_message_id": message_id,
        "prospect_id": message.prospect_id if message else None,
        "sender_account_id": message.sender_account_id if message else None,
        "safe_metadata_json": {
            "has_message_id": bool(message_id),
            "agentmail_event_type": event_type,
        },
    }


def _suppress_bounced_recipients(payload: dict[str, Any]) -> None:
    bounce = payload.get("bounce")
    if not isinstance(bounce, dict):
        return
    for recipient in bounce.get("recipients") or []:
        address = recipient.get("address") if isinstance(recipient, dict) else recipient
        if address and "@" in address:
            record_suppression(email=address, reason="hard_bounce", source="agentmail")


def _extract_reply_text(payload: dict[str, Any]) -> str | None:
    message = payload.get("message")
    if not isinstance(message, dict):
        return None
    return message.get("extracted_text") or message.get("text") or message.get("preview")


def _transition_prospect(prospect_id: int | None, status: str, message: str) -> None:
    if not prospect_id:
        return
    prospect = get_prospect(prospect_id)
    if not prospect:
        return
    try:
        transition_prospect_status(prospect_id, status, event_message=message, event_details={"source": "agentmail"})
    except InvalidProspectTransition:
        return
    if status in {"bounced", "complained"}:
        record_suppression(email=prospect.email, reason=status, source="agentmail")


def _handle_unsubscribe_reply(prospect_id: int | None) -> None:
    if not prospect_id:
        return
    prospect = get_prospect(prospect_id)
    if not prospect:
        return
    record_suppression(email=prospect.email, reason="unsubscribe_reply", source="agentmail")
    mark_unsent_messages_for_prospect_status(prospect.id, "skipped")
    try:
        transition_prospect_status(
            prospect.id,
            "unsubscribed",
            event_message="Prospect unsubscribed by reply.",
            event_details={"source": "agentmail"},
        )
    except InvalidProspectTransition:
        return


def _suppress_prospect_email(prospect_id: int | None, reason: str) -> None:
    if not prospect_id:
        return
    prospect = get_prospect(prospect_id)
    if prospect:
        record_suppression(email=prospect.email, reason=reason, source="agentmail")


def _mark_message_status(agentmail_message_id: str | None, status: str) -> None:
    if not agentmail_message_id:
        return
    message = get_message_by_agentmail_message_id(agentmail_message_id)
    if message:
        update_message_status(message.id, status)


def _alert_for_reply_triage(classification: str, suggested_response_angle: str | None) -> None:
    if classification == "positive":
        _alert_founder("high", "Positive reply to Tempa sales email.", suggested_response_angle or "Review and reply manually.")
    elif classification == "objection":
        _alert_founder("normal", "Objection reply to Tempa sales email.", suggested_response_angle or "Review and reply manually.")
    elif classification == "angry":
        _alert_founder("high", "Angry reply to Tempa sales email.", "Suppress, review sender health, and do not auto-reply.")
    elif classification == "unknown":
        _alert_founder("normal", "Unclear reply to Tempa sales email.", "Review manually before taking action.")


def _alert_founder(severity: str, summary: str, recommended_action: str) -> None:
    record_signal(
        SignalInput(
            source="tempa_sales_agent",
            kind="sales_reply",
            venture="tempa",
            severity=severity,
            summary=summary,
            recommended_action=recommended_action,
        )
    )
