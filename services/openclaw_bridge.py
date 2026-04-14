"""Bridge Slack messages into OpenClaw's Gateway chat surface."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


class OpenClawBridgeError(RuntimeError):
    """Raised when OpenClaw cannot answer a Slack message."""


@dataclass
class OpenClawChatResult:
    text: str


def is_openclaw_chat_configured() -> bool:
    return bool(os.getenv("OPENCLAW_CHAT_BASE_URL", "").strip())


def send_openclaw_chat_message(
    message: str,
    *,
    session_key: str,
    slack_user_id: str,
    timeout_seconds: float = 120.0,
) -> OpenClawChatResult:
    """Send a founder message to OpenClaw and return the assistant response.

    OpenClaw's Gateway exposes an OpenAI-compatible HTTP endpoint when enabled.
    The gateway still owns the real agent run, tools, permissions, and session
    behavior; this function is only the transport from Slack into that surface.
    """

    base_url = os.getenv("OPENCLAW_CHAT_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        raise OpenClawBridgeError("OPENCLAW_CHAT_BASE_URL is not configured.")

    token = os.getenv("OPENCLAW_GATEWAY_TOKEN", "").strip()
    model = os.getenv("OPENCLAW_CHAT_MODEL", "openclaw/default").strip() or "openclaw/default"

    headers = {
        "Content-Type": "application/json",
        "x-openclaw-session-key": session_key,
        "x-openclaw-message-channel": "slack-control-bridge",
        "x-openclaw-slack-user-id": slack_user_id,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = httpx.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json={
            "model": model,
            "messages": [{"role": "user", "content": message}],
            "stream": False,
            "user": session_key,
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenClawBridgeError(f"OpenClaw returned an unexpected response shape: {payload}") from exc

    text = str(content or "").strip()
    if not text:
        raise OpenClawBridgeError("OpenClaw returned an empty response.")
    return OpenClawChatResult(text=text)
