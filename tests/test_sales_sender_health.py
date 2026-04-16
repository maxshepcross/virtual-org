"""Tests for sales sender health automation."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from models.sales import SalesSenderAccount
from services.sales_sender_health import SalesSenderHealthService


class SalesSenderHealthServiceTests(unittest.TestCase):
    def _sender(self, *, verified: bool = True, status: str = "active") -> SalesSenderAccount:
        return SalesSenderAccount(
            id=4,
            agent_id=2,
            email="sender@example.com",
            inbox_id="inbox_1",
            status=status,
            verified=verified,
        )

    @patch("services.sales_sender_health.pause_sender_account")
    @patch("services.sales_sender_health.latest_sender_sent_at")
    @patch("services.sales_sender_health.latest_sender_webhook_event_at")
    @patch("services.sales_sender_health.count_sender_events_since")
    @patch("services.sales_sender_health.count_sender_sent_since")
    def test_pauses_sender_after_spam_complaint(
        self,
        count_sender_sent_since,
        count_sender_events_since,
        latest_sender_event_at,
        latest_sender_sent_at,
        pause_sender_account,
    ) -> None:
        count_sender_sent_since.return_value = 20
        count_sender_events_since.side_effect = [0, 1]
        latest_sender_event_at.return_value = datetime.now(timezone.utc)
        latest_sender_sent_at.return_value = datetime.now(timezone.utc)
        pause_sender_account.return_value = self._sender(status="paused")

        result = SalesSenderHealthService().evaluate_sender(self._sender(), send_mode="live")

        self.assertEqual(result.status, "paused")
        self.assertIn("Spam complaint", result.pause_reason)
        pause_sender_account.assert_called_once()

    @patch("services.sales_sender_health.pause_sender_account")
    @patch("services.sales_sender_health.latest_sender_sent_at")
    @patch("services.sales_sender_health.latest_sender_webhook_event_at")
    @patch("services.sales_sender_health.count_sender_events_since")
    @patch("services.sales_sender_health.count_sender_sent_since")
    def test_pauses_sender_when_bounce_rate_exceeds_threshold(
        self,
        count_sender_sent_since,
        count_sender_events_since,
        latest_sender_event_at,
        latest_sender_sent_at,
        pause_sender_account,
    ) -> None:
        count_sender_sent_since.return_value = 100
        count_sender_events_since.side_effect = [4, 0]
        latest_sender_event_at.return_value = datetime.now(timezone.utc)
        latest_sender_sent_at.return_value = datetime.now(timezone.utc)
        pause_sender_account.return_value = self._sender(status="paused")

        result = SalesSenderHealthService().evaluate_sender(self._sender(), send_mode="live")

        self.assertEqual(result.bounce_rate_7d, 0.04)
        self.assertIn("Hard bounce rate", result.pause_reason)

    @patch("services.sales_sender_health.pause_sender_account")
    @patch("services.sales_sender_health.latest_sender_sent_at")
    @patch("services.sales_sender_health.latest_sender_webhook_event_at")
    @patch("services.sales_sender_health.count_sender_events_since")
    @patch("services.sales_sender_health.count_sender_sent_since")
    def test_pauses_sender_when_webhook_events_are_stale(
        self,
        count_sender_sent_since,
        count_sender_events_since,
        latest_sender_event_at,
        latest_sender_sent_at,
        pause_sender_account,
    ) -> None:
        count_sender_sent_since.return_value = 20
        count_sender_events_since.side_effect = [0, 0]
        latest_sender_sent_at.return_value = datetime.now(timezone.utc) - timedelta(hours=25)
        latest_sender_event_at.return_value = None
        pause_sender_account.return_value = self._sender(status="paused")

        result = SalesSenderHealthService().evaluate_sender(self._sender(), send_mode="live")

        self.assertIn("stale", result.pause_reason)

    @patch("services.sales_sender_health.pause_sender_account")
    @patch("services.sales_sender_health.latest_sender_sent_at")
    @patch("services.sales_sender_health.latest_sender_webhook_event_at")
    @patch("services.sales_sender_health.count_sender_events_since")
    @patch("services.sales_sender_health.count_sender_sent_since")
    def test_pauses_unverified_sender_in_live_mode(
        self,
        count_sender_sent_since,
        count_sender_events_since,
        latest_sender_event_at,
        latest_sender_sent_at,
        pause_sender_account,
    ) -> None:
        count_sender_sent_since.return_value = 0
        count_sender_events_since.side_effect = [0, 0]
        latest_sender_event_at.return_value = None
        latest_sender_sent_at.return_value = None
        pause_sender_account.return_value = self._sender(status="paused", verified=False)

        result = SalesSenderHealthService().evaluate_sender(self._sender(verified=False), send_mode="live")

        self.assertIn("verification", result.pause_reason)


if __name__ == "__main__":
    unittest.main()
