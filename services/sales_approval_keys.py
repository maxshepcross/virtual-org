"""Approval keys for exact sales-message live-send checks."""

from __future__ import annotations

import hashlib


def sales_message_approval_event_id(*, agent_id: int, message_id: int, subject: str, body: str) -> str:
    content_hash = hashlib.sha256(f"{subject}\n{body}".encode("utf-8")).hexdigest()[:16]
    return f"sales:first-live:{agent_id}:message:{message_id}:{content_hash}"
