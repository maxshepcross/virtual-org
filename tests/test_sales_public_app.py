"""Tests for the public sales app boundary."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.sales_public_app import app


class SalesPublicAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_healthcheck_returns_ok(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    @patch("api.sales_public_app._preview_service")
    def test_preview_sets_noindex_header(self, preview_service) -> None:
        preview_service.resolve_preview.return_value = ("valid", "<html>ok</html>")

        response = self.client.get("/v1/sales/preview/token")

        self.assertEqual(response.status_code, 200)
        self.assertIn("noindex", response.headers["x-robots-tag"])
        self.assertIn("no-store", response.headers["cache-control"])

    @patch("api.sales_public_app._preview_service")
    def test_unsubscribe_form_escapes_token(self, preview_service) -> None:
        response = self.client.get("/v1/sales/unsubscribe/bad%22%3E%3Cscript%3E")

        self.assertEqual(response.status_code, 200)
        self.assertIn("bad&quot;&gt;&lt;script&gt;", response.text)
        self.assertNotIn('bad"><script>', response.text)

    @patch("api.sales_public_app._preview_service")
    def test_unsubscribe_invalid_token_does_not_claim_success(self, preview_service) -> None:
        preview_service.unsubscribe.return_value = False

        response = self.client.post("/v1/sales/unsubscribe/missing-token")

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.text)

    def test_webhook_rejects_oversized_payload_before_signature_check(self) -> None:
        with patch("api.sales_public_app.MAX_WEBHOOK_BODY_BYTES", 4):
            response = self.client.post(
                "/v1/sales/webhooks/agentmail",
                content=b"x" * 8,
            )

        self.assertEqual(response.status_code, 413)

    @patch("api.sales_public_app.AgentMailService")
    def test_webhook_rejects_invalid_signature(self, service_class) -> None:
        service_class.return_value.verify_webhook.side_effect = PermissionError("Invalid AgentMail webhook signature.")

        response = self.client.post("/v1/sales/webhooks/agentmail", content=b"{}")

        self.assertEqual(response.status_code, 401)

    @patch("api.sales_public_app.get_message_by_agentmail_message_id")
    @patch("api.sales_public_app.record_send_event")
    @patch("api.sales_public_app.AgentMailService")
    def test_webhook_dedupes_existing_event(self, service_class, record_send_event, get_message) -> None:
        service_class.return_value.verify_webhook.return_value = {
            "event_id": "evt_1",
            "event_type": "message.delivered",
            "delivery": {"message_id": "msg_1"},
        }
        record_send_event.return_value = None
        get_message.return_value = None

        response = self.client.post("/v1/sales/webhooks/agentmail", content=b"{}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "deduped")

    @patch("api.sales_public_app._alert_for_reply_triage")
    @patch("api.sales_public_app._handle_unsubscribe_reply")
    @patch("api.sales_public_app._transition_prospect")
    @patch("api.sales_public_app.record_reply_triage_event")
    @patch("api.sales_public_app.get_message_by_agentmail_message_id")
    @patch("api.sales_public_app.record_send_event")
    @patch("api.sales_public_app.AgentMailService")
    def test_received_reply_is_triaged(
        self,
        service_class,
        record_send_event,
        get_message,
        record_reply_triage_event,
        transition_prospect,
        handle_unsubscribe_reply,
        alert_for_reply_triage,
    ) -> None:
        service_class.return_value.verify_webhook.return_value = {
            "event_id": "evt_2",
            "event_type": "message.received",
            "message": {"message_id": "msg_2", "text": "Interested, can we book a demo?"},
        }
        get_message.return_value = type("Message", (), {"prospect_id": 7, "sender_account_id": 3})()
        record_send_event.return_value = type("Event", (), {"id": 99})()

        response = self.client.post("/v1/sales/webhooks/agentmail", content=b"{}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["classification"], "positive")
        record_reply_triage_event.assert_called_once()
        transition_prospect.assert_called_once()
        alert_for_reply_triage.assert_called_once()

    @patch("api.sales_public_app._alert_for_reply_triage")
    @patch("api.sales_public_app._handle_unsubscribe_reply")
    @patch("api.sales_public_app._transition_prospect")
    @patch("api.sales_public_app.record_reply_triage_event")
    @patch("api.sales_public_app.get_message_by_agentmail_message_id")
    @patch("api.sales_public_app.record_send_event")
    @patch("api.sales_public_app.AgentMailService")
    def test_unsubscribe_reply_suppresses_instead_of_marking_replied(
        self,
        service_class,
        record_send_event,
        get_message,
        record_reply_triage_event,
        transition_prospect,
        handle_unsubscribe_reply,
        alert_for_reply_triage,
    ) -> None:
        service_class.return_value.verify_webhook.return_value = {
            "event_id": "evt_3",
            "event_type": "message.received",
            "message": {"message_id": "msg_3", "text": "Please unsubscribe me"},
        }
        get_message.return_value = type("Message", (), {"prospect_id": 7, "sender_account_id": 3})()
        record_send_event.return_value = type("Event", (), {"id": 100})()

        response = self.client.post("/v1/sales/webhooks/agentmail", content=b"{}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["classification"], "unsubscribe")
        handle_unsubscribe_reply.assert_called_once_with(7)
        transition_prospect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
