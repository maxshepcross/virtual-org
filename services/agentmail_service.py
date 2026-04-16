"""AgentMail client and webhook verification.

AgentMail docs checked: https://docs.agentmail.to
Send endpoint: POST /v0/inboxes/{inbox_id}/messages/send.
Webhook events use Svix headers.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from pydantic import BaseModel


AGENTMAIL_API_BASE = "https://api.agentmail.to"


class AgentMailSendRequest(BaseModel):
    inbox_id: str
    to: str
    subject: str
    text: str
    reply_to: str | None = None
    headers: dict[str, str] | None = None


class AgentMailSendResult(BaseModel):
    message_id: str
    thread_id: str | None = None
    raw_json: dict[str, Any]


class AgentMailService:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        webhook_secret: str | None = None,
        base_url: str = AGENTMAIL_API_BASE,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("AGENTMAIL_API_KEY", "").strip()
        self.webhook_secret = (
            webhook_secret if webhook_secret is not None else os.getenv("AGENTMAIL_WEBHOOK_SECRET", "").strip()
        )
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def send_message(self, request: AgentMailSendRequest) -> AgentMailSendResult:
        if not self.api_key:
            raise RuntimeError("AGENTMAIL_API_KEY is not configured.")
        payload: dict[str, Any] = {
            "to": request.to,
            "subject": request.subject,
            "text": request.text,
            "headers": request.headers or {},
        }
        if request.reply_to:
            payload["reply_to"] = request.reply_to

        response = httpx.post(
            f"{self.base_url}/v0/inboxes/{request.inbox_id}/messages/send",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "accept": "application/json",
                "content-type": "application/json",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        raw = response.json()
        return AgentMailSendResult(
            message_id=raw["message_id"],
            thread_id=raw.get("thread_id"),
            raw_json=raw,
        )

    def verify_webhook(self, payload: bytes, headers: dict[str, str]) -> dict[str, Any]:
        if not self.webhook_secret:
            raise RuntimeError("AGENTMAIL_WEBHOOK_SECRET is not configured.")
        try:
            from svix.webhooks import Webhook
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("The svix package is required for AgentMail webhook verification.") from exc

        webhook = Webhook(self.webhook_secret)
        try:
            webhook.verify(payload, headers)
        except Exception as exc:
            raise PermissionError("Invalid AgentMail webhook signature.") from exc
        return json.loads(payload.decode("utf-8"))
