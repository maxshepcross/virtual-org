"""Sender health checks for the Tempa sales worker."""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone

from pydantic import BaseModel

from models.sales import (
    SalesSenderAccount,
    count_sender_events_since,
    count_sender_sent_since,
    latest_sender_event_at,
    latest_sender_webhook_event_at,
    latest_sender_sent_at,
    pause_sender_account,
)


logger = logging.getLogger(__name__)


class SenderHealthResult(BaseModel):
    sender_account_id: int
    email: str
    status: str
    sent_7d: int
    bounces_7d: int
    complaints_7d: int
    bounce_rate_7d: float
    latest_event_at: datetime | None = None
    latest_sent_at: datetime | None = None
    pause_reason: str | None = None


class SalesSenderHealthService:
    def evaluate_sender(self, sender: SalesSenderAccount, *, send_mode: str | None = None) -> SenderHealthResult:
        mode = send_mode or os.getenv("SALES_SEND_MODE", "dry_run")
        sent_7d = count_sender_sent_since(sender.id, days=7)
        bounces_7d = count_sender_events_since(sender.id, event_type="message.bounced", days=7)
        complaints_7d = count_sender_events_since(sender.id, event_type="message.complained", days=7)
        latest_event = latest_sender_webhook_event_at(sender.id)
        latest_sent = latest_sender_sent_at(sender.id)
        bounce_rate = (bounces_7d / sent_7d) if sent_7d else 0.0

        pause_reason = self._pause_reason(
            sender=sender,
            send_mode=mode,
            sent_7d=sent_7d,
            bounces_7d=bounces_7d,
            complaints_7d=complaints_7d,
            latest_event_at=latest_event,
            latest_sent_at=latest_sent,
        )
        status = sender.status
        if pause_reason and sender.status != "paused":
            paused = pause_sender_account(sender.id, pause_reason)
            status = paused.status if paused else "paused"
            logger.info(
                "sales_sender_paused_by_health",
                extra={"sender_account_id": sender.id, "reason": pause_reason, "send_mode": mode},
            )

        return SenderHealthResult(
            sender_account_id=sender.id,
            email=sender.email,
            status=status,
            sent_7d=sent_7d,
            bounces_7d=bounces_7d,
            complaints_7d=complaints_7d,
            bounce_rate_7d=bounce_rate,
            latest_event_at=latest_event,
            latest_sent_at=latest_sent,
            pause_reason=pause_reason or sender.pause_reason,
        )

    def _pause_reason(
        self,
        *,
        sender: SalesSenderAccount,
        send_mode: str,
        sent_7d: int,
        bounces_7d: int,
        complaints_7d: int,
        latest_event_at: datetime | None,
        latest_sent_at: datetime | None,
    ) -> str | None:
        if send_mode == "live" and not sender.verified:
            return "Sender domain verification is missing."
        if complaints_7d > 0:
            return "Spam complaint received in the last 7 days."
        if sent_7d >= 10 and (bounces_7d / sent_7d) > 0.03:
            return "Hard bounce rate exceeded 3 percent over 7 days."
        if self._events_are_stale(latest_sent_at=latest_sent_at, latest_event_at=latest_event_at):
            return "AgentMail event processing is stale for more than 24 hours."
        return None

    def _events_are_stale(self, *, latest_sent_at: datetime | None, latest_event_at: datetime | None) -> bool:
        if not latest_sent_at:
            return False
        now = datetime.now(timezone.utc)
        sent_at = self._aware(latest_sent_at)
        if (now - sent_at).total_seconds() <= 24 * 60 * 60:
            return False
        if not latest_event_at:
            return True
        return self._aware(latest_event_at) < sent_at

    def _aware(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
