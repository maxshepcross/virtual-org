"""Tests for the dedicated sales send worker."""

import os
import unittest
from unittest.mock import patch
from unittest.mock import Mock

from models.sales import SalesOutreachMessage, SalesSenderAccount
from services.sales_send_worker import SalesSendWorker, SalesWorkerResult


class SalesSendWorkerTests(unittest.TestCase):
    def _active_agent(self, *, send_mode: str = "dry_run"):
        return type("Agent", (), {"id": 1, "status": "active", "send_mode": send_mode})()

    def _message(self) -> SalesOutreachMessage:
        return SalesOutreachMessage(
            id=8,
            agent_id=1,
            prospect_id=4,
            personalization_id=9,
            subject="Paid social idea for Acme",
            body="Body",
            status="sending",
        )

    def test_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {"SALES_AGENT_ENABLED": "false"}, clear=False):
            result = SalesSendWorker().run_once(1)
        self.assertEqual(result.action, "disabled")

    def test_kill_switch_blocks_worker(self) -> None:
        with patch.dict(
            os.environ,
            {"SALES_AGENT_ENABLED": "true", "SALES_KILL_SWITCH": "true"},
            clear=False,
        ):
            result = SalesSendWorker().run_once(1)
        self.assertEqual(result.action, "blocked")

    @patch("services.sales_send_worker.get_sales_agent")
    def test_paused_agent_blocks_worker_even_when_env_is_enabled(self, get_sales_agent) -> None:
        get_sales_agent.return_value = type("Agent", (), {"id": 1, "status": "paused", "send_mode": "live"})()

        with patch.dict(
            os.environ,
            {"SALES_AGENT_ENABLED": "true", "SALES_KILL_SWITCH": "false", "SALES_SEND_MODE": "live"},
            clear=False,
        ):
            result = SalesSendWorker().run_once(1)

        self.assertEqual(result.action, "blocked")
        self.assertEqual(result.message, "Sales agent is paused.")

    @patch("services.sales_send_worker.get_sales_agent")
    def test_live_env_requires_agent_live_mode_too(self, get_sales_agent) -> None:
        get_sales_agent.return_value = self._active_agent(send_mode="dry_run")

        with patch.dict(
            os.environ,
            {"SALES_AGENT_ENABLED": "true", "SALES_KILL_SWITCH": "false", "SALES_SEND_MODE": "live"},
            clear=False,
        ):
            result = SalesSendWorker().run_once(1)

        self.assertEqual(result.action, "blocked")
        self.assertIn("not configured for live", result.message)

    def test_live_send_requires_verified_sender_and_compliance_settings(self) -> None:
        worker = SalesSendWorker()
        message = self._message()
        with patch("services.sales_send_worker.external_approval_is_approved", return_value=False):
            self.assertEqual(
                worker._live_send_block_reason("live", False, agent_id=7, message=message),
                "This exact live sales message has not been approved in Slack.",
            )
        with patch("services.sales_send_worker.external_approval_is_approved", return_value=True):
            self.assertEqual(
                worker._live_send_block_reason("live", False, agent_id=7, message=message),
                "Sender account is not verified.",
            )
        with patch("services.sales_send_worker.external_approval_is_approved", return_value=True), patch.dict(
            os.environ,
            {
                "AGENTMAIL_SENDER_DOMAIN": "sales.example.com",
                "SALES_POSTAL_ADDRESS": "1 Main St",
                "SALES_UNSUBSCRIBE_BASE_URL": "https://example.com/u",
            },
            clear=False,
        ):
            self.assertIsNone(worker._live_send_block_reason("live", True, agent_id=7, message=message))

    def test_run_loop_stops_when_worker_is_disabled(self) -> None:
        worker = SalesSendWorker()
        with patch.object(worker, "run_once", return_value=SalesWorkerResult(action="disabled", message="off")):
            result = worker.run_loop(1, max_passes=5, sleep_fn=lambda _: None)

        self.assertEqual(result.action, "disabled")
        self.assertEqual(result.passes, 1)
        self.assertEqual(result.sent, 0)

    def test_run_loop_accumulates_sent_counts(self) -> None:
        worker = SalesSendWorker()
        with patch.object(
            worker,
            "run_once",
            side_effect=[
                SalesWorkerResult(action="sent", message="ok", sent=1),
                SalesWorkerResult(action="idle", message="none", sent=0),
            ],
        ):
            result = worker.run_loop(1, max_passes=2, sleep_fn=lambda _: None)

        self.assertEqual(result.action, "completed")
        self.assertEqual(result.passes, 2)
        self.assertEqual(result.sent, 1)
        self.assertEqual(result.last_result.action, "idle")

    def test_run_loop_can_stop_on_blocked_result(self) -> None:
        worker = SalesSendWorker()
        with patch.object(worker, "run_once", return_value=SalesWorkerResult(action="blocked", message="kill switch")):
            result = worker.run_loop(1, max_passes=5, stop_on_blocked=True, sleep_fn=lambda _: None)

        self.assertEqual(result.action, "blocked")
        self.assertEqual(result.passes, 1)

    @patch("services.sales_send_worker.get_sales_agent")
    @patch("services.sales_send_worker.list_sender_accounts")
    def test_run_once_blocks_when_all_senders_are_unhealthy(self, list_sender_accounts, get_sales_agent) -> None:
        get_sales_agent.return_value = self._active_agent()
        sender = SalesSenderAccount(
            id=4,
            agent_id=1,
            email="sender@example.com",
            inbox_id="inbox_1",
            status="active",
            verified=True,
        )
        list_sender_accounts.return_value = [sender]
        health_service = Mock()
        health_service.evaluate_sender.return_value = type("Health", (), {"pause_reason": "Spam complaint"})()

        with patch.dict(
            os.environ,
            {"SALES_AGENT_ENABLED": "true", "SALES_KILL_SWITCH": "false"},
            clear=False,
        ):
            result = SalesSendWorker(health_service=health_service).run_once(1)

        self.assertEqual(result.action, "blocked")
        self.assertEqual(result.message, "No healthy active sender accounts.")

    @patch("services.sales_send_worker.release_claimed_message")
    @patch("services.sales_send_worker.record_send_event")
    @patch("services.sales_send_worker.list_sales_messages")
    @patch("services.sales_send_worker.is_suppressed")
    @patch("services.sales_send_worker.get_prospect")
    @patch("services.sales_send_worker.claim_next_ready_message")
    @patch("services.sales_send_worker.list_sender_accounts")
    @patch("services.sales_send_worker.get_sales_agent")
    def test_dry_run_claims_message_and_only_counts_new_event(
        self,
        get_sales_agent,
        list_sender_accounts,
        claim_next_ready_message,
        get_prospect,
        is_suppressed,
        list_sales_messages,
        record_send_event,
        release_claimed_message,
    ) -> None:
        get_sales_agent.return_value = self._active_agent()
        list_sender_accounts.return_value = [
            SalesSenderAccount(id=4, agent_id=1, email="sender@example.com", inbox_id="inbox_1", status="active", verified=True)
        ]
        claim_next_ready_message.side_effect = [self._message(), None]
        get_prospect.return_value = type("Prospect", (), {"id": 4, "email": "ada@example.com", "company_domain": "acme.com"})()
        is_suppressed.return_value = False
        list_sales_messages.return_value = []
        record_send_event.return_value = type("Event", (), {"id": 99})()

        with patch.dict(
            os.environ,
            {"SALES_AGENT_ENABLED": "true", "SALES_KILL_SWITCH": "false", "SALES_SEND_MODE": "dry_run"},
            clear=False,
        ):
            health_service = Mock()
            health_service.evaluate_sender.return_value = type("Health", (), {"pause_reason": None})()
            worker = SalesSendWorker(health_service=health_service)
            result = worker.run_once(1)

        self.assertEqual(result.action, "sent")
        self.assertEqual(result.sent, 1)
        release_claimed_message.assert_called_once_with(8, clear_sender=True)

    @patch("services.sales_send_worker.release_claimed_message")
    @patch("services.sales_send_worker.get_latest_eval_result")
    @patch("services.sales_send_worker.is_suppressed")
    @patch("services.sales_send_worker.get_prospect")
    @patch("services.sales_send_worker.claim_next_ready_message")
    @patch("services.sales_send_worker.list_sender_accounts")
    @patch("services.sales_send_worker.get_sales_agent")
    @patch("services.sales_send_worker.external_approval_is_approved")
    def test_live_send_blocks_without_llm_eval(
        self,
        external_approval_is_approved,
        get_sales_agent,
        list_sender_accounts,
        claim_next_ready_message,
        get_prospect,
        is_suppressed,
        get_latest_eval_result,
        release_claimed_message,
    ) -> None:
        external_approval_is_approved.return_value = True
        get_sales_agent.return_value = self._active_agent(send_mode="live")
        list_sender_accounts.return_value = [
            SalesSenderAccount(id=4, agent_id=1, email="sender@example.com", inbox_id="inbox_1", status="active", verified=True)
        ]
        claim_next_ready_message.return_value = self._message()
        get_prospect.return_value = type("Prospect", (), {"id": 4, "email": "ada@example.com", "company_domain": "acme.com"})()
        is_suppressed.return_value = False
        get_latest_eval_result.return_value = type("Eval", (), {"status": "passed", "llm_passed": None})()

        with patch.dict(
            os.environ,
            {
                "SALES_AGENT_ENABLED": "true",
                "SALES_KILL_SWITCH": "false",
                "SALES_SEND_MODE": "live",
                "AGENTMAIL_SENDER_DOMAIN": "sales.example.com",
                "SALES_POSTAL_ADDRESS": "1 Main St",
                "SALES_UNSUBSCRIBE_BASE_URL": "https://sales.example.com/u",
            },
            clear=False,
        ):
            worker = SalesSendWorker()
            worker.health_service.evaluate_sender = Mock(return_value=type("Health", (), {"pause_reason": None})())
            result = worker.run_once(1)

        self.assertEqual(result.action, "blocked")
        self.assertIn("LLM rubric", result.message)
        release_claimed_message.assert_called_once_with(8)

    @patch("services.sales_send_worker.mark_claimed_message_status")
    @patch("services.sales_send_worker.list_sales_messages")
    @patch("services.sales_send_worker.transition_prospect_status")
    @patch("services.sales_send_worker.get_latest_eval_result")
    @patch("services.sales_send_worker.is_suppressed")
    @patch("services.sales_send_worker.get_prospect")
    @patch("services.sales_send_worker.claim_next_ready_message")
    @patch("services.sales_send_worker.list_sender_accounts")
    @patch("services.sales_send_worker.get_sales_agent")
    @patch("services.sales_send_worker.external_approval_is_approved")
    def test_live_send_rechecks_suppression_immediately_before_send(
        self,
        external_approval_is_approved,
        get_sales_agent,
        list_sender_accounts,
        claim_next_ready_message,
        get_prospect,
        is_suppressed,
        get_latest_eval_result,
        transition_prospect_status,
        list_sales_messages,
        mark_claimed_message_status,
    ) -> None:
        external_approval_is_approved.return_value = True
        get_sales_agent.return_value = self._active_agent(send_mode="live")
        list_sender_accounts.return_value = [
            SalesSenderAccount(id=4, agent_id=1, email="sender@example.com", inbox_id="inbox_1", status="active", verified=True)
        ]
        claim_next_ready_message.side_effect = [self._message(), None]
        get_prospect.return_value = type("Prospect", (), {"id": 4, "email": "ada@example.com", "company_domain": "acme.com"})()
        is_suppressed.side_effect = [False, True]
        get_latest_eval_result.return_value = type("Eval", (), {"status": "passed", "llm_passed": True})()
        list_sales_messages.return_value = []

        with patch.dict(
            os.environ,
            {
                "SALES_AGENT_ENABLED": "true",
                "SALES_KILL_SWITCH": "false",
                "SALES_SEND_MODE": "live",
                "AGENTMAIL_SENDER_DOMAIN": "sales.example.com",
                "SALES_POSTAL_ADDRESS": "1 Main St",
                "SALES_UNSUBSCRIBE_BASE_URL": "https://sales.example.com/u",
            },
            clear=False,
        ):
            worker = SalesSendWorker(agentmail=Mock())
            worker.health_service.evaluate_sender = Mock(return_value=type("Health", (), {"pause_reason": None})())
            result = worker.run_once(1)

        self.assertEqual(result.action, "idle")
        mark_claimed_message_status.assert_called_once_with(8, "skipped")
        worker.agentmail.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
