"""Tests for the sales workflow owner."""

import os
import unittest
from unittest.mock import Mock, patch

from models.sales import SalesOutreachMessage, SalesPersonalization, SalesPreviewToken, SalesProspect, SalesEvalResult
from services.apollo_sales_source import ApolloSearchRequest
from services.sales_agent_service import SalesAgentService


GOOD_STRATEGY = {
    "company": "Acme",
    "prospect": "Ada",
    "evidence_urls": ["https://example.com/acme"],
    "observed_growth_context": "recent product launch",
    "suggested_paid_social_angle": "founder-led demo clip",
    "target_audience": "startup founders",
    "example_ad_concept": "30-second walkthrough",
    "why_tempa_can_help": "quick creative testing",
    "confidence_score": 0.91,
}


class SalesAgentServiceTests(unittest.TestCase):
    def _prospect(self) -> SalesProspect:
        return SalesProspect(
            id=4,
            agent_id=2,
            source="manual_seed",
            email="ada@example.com",
            normalized_email_hash="hash",
            first_name="Ada",
            company_name="Acme",
            company_domain="acme.com",
            status="imported",
        )

    def _message(self) -> SalesOutreachMessage:
        return SalesOutreachMessage(
            id=8,
            agent_id=2,
            prospect_id=4,
            personalization_id=9,
            subject="Paid social idea for Acme",
            body="Hi Ada,\nhttps://sales.example.com/v1/sales/preview/preview-token\nUnsubscribe: https://sales.example.com/u",
            status="ready_to_send",
        )

    @patch("services.sales_agent_service.create_prospect")
    def test_apollo_import_maps_valid_people_and_skips_invalid_rows(self, create_prospect) -> None:
        apollo_source = Mock()
        apollo_source.search_people.return_value = [
            {
                "id": "person_1",
                "email": "ada@example.com",
                "first_name": "Ada",
                "last_name": "Lovelace",
                "title": "Founder",
                "country": "US",
                "organization": {
                    "id": "org_1",
                    "name": "Acme",
                    "primary_domain": "acme.com",
                    "website_url": "https://acme.com",
                },
            },
            {
                "id": "person_2",
                "email": "",
                "first_name": "No",
                "organization": {"name": "Missing Email Co"},
            },
            {
                "id": "person_3",
                "email": "au@example.com",
                "country": "AU",
                "organization": {"name": "Australia Co", "primary_domain": "australia.example"},
            },
        ]
        create_prospect.return_value = self._prospect()

        with patch.dict(os.environ, {"SALES_ALLOWED_RECIPIENT_COUNTRIES": "US"}, clear=False):
            result = SalesAgentService(apollo_source=apollo_source).import_prospects(
                2,
                request=type(
                    "Request",
                    (),
                    {
                        "source": "apollo",
                        "apollo_search": ApolloSearchRequest(per_page=10),
                        "prospects": [],
                    },
                )(),
            )

        self.assertEqual(result.imported, 1)
        self.assertEqual(result.skipped_invalid, 2)
        create_prospect.assert_called_once()
        self.assertEqual(create_prospect.call_args.kwargs["source"], "apollo")
        self.assertEqual(create_prospect.call_args.kwargs["company_domain"], "acme.com")

    @patch("services.sales_agent_service.create_prospect")
    def test_apollo_import_counts_duplicates(self, create_prospect) -> None:
        apollo_source = Mock()
        apollo_source.search_people.return_value = [
            {
                "id": "person_1",
                "email": "ada@example.com",
                "country": "US",
                "organization": {"name": "Acme", "primary_domain": "acme.com"},
            }
        ]
        create_prospect.return_value = None

        result = SalesAgentService(apollo_source=apollo_source).import_prospects(
            2,
            request=type(
                "Request",
                (),
                {
                    "source": "apollo",
                    "apollo_search": ApolloSearchRequest(),
                    "prospects": [],
                },
            )(),
        )

        self.assertEqual(result.imported, 0)
        self.assertEqual(result.skipped_duplicates, 1)

    @patch("services.sales_agent_service.list_sender_accounts")
    @patch("services.sales_agent_service.list_sales_agents")
    def test_health_includes_live_approval_status_and_senders(
        self,
        list_sales_agents,
        list_sender_accounts,
    ) -> None:
        list_sales_agents.return_value = [
            type(
                "Agent",
                (),
                {
                    "id": 3,
                    "model_dump": lambda self: {"id": 3, "venture": "tempa"},
                },
            )()
        ]
        list_sender_accounts.return_value = [
            type("Sender", (), {"model_dump": lambda self: {"email": "sender@example.com"}})()
        ]

        health_service = Mock()
        health_service.evaluate_sender.return_value.model_dump.return_value = {"pause_reason": None, "bounce_rate_7d": 0.0}

        result = SalesAgentService(sender_health_service=health_service).health()

        self.assertEqual(result["agents"][0]["first_live_approval_status"], "message_scoped")
        self.assertEqual(result["agents"][0]["senders"][0]["email"], "sender@example.com")
        self.assertEqual(result["agents"][0]["senders"][0]["health"]["bounce_rate_7d"], 0.0)

    @patch("services.sales_agent_service.get_latest_eval_result")
    @patch("services.sales_agent_service.get_personalization")
    @patch("services.sales_agent_service.get_prospect")
    @patch("services.sales_agent_service.list_sales_messages")
    def test_dry_run_summary_includes_email_preview_and_eval_reasons(
        self,
        list_sales_messages,
        get_prospect,
        get_personalization,
        get_latest_eval_result,
    ) -> None:
        list_sales_messages.return_value = [self._message()]
        get_prospect.return_value = self._prospect()
        get_personalization.return_value = SalesPersonalization(
            id=9,
            prospect_id=4,
            strategy_json=GOOD_STRATEGY,
            email_subject="Paid social idea for Acme",
            email_body="Body",
        )
        get_latest_eval_result.return_value = SalesEvalResult(
            id=5,
            prospect_id=4,
            personalization_id=9,
            status="passed",
            deterministic_passed=True,
            llm_passed=True,
        )

        summary = SalesAgentService().dry_run_summary(2)

        self.assertEqual(summary.ready_count, 1)
        self.assertEqual(summary.blocked_count, 0)
        self.assertEqual(summary.first_live_approval_status, "message_scoped")
        self.assertEqual(summary.items[0].company_name, "Acme")
        self.assertEqual(summary.items[0].preview_link, "https://sales.example.com/v1/sales/preview/preview-token")
        self.assertIn("Required strategy fields are present.", summary.items[0].passed_reasons)

    @patch("services.sales_agent_service.get_latest_eval_result")
    @patch("services.sales_agent_service.get_personalization")
    @patch("services.sales_agent_service.get_prospect")
    @patch("services.sales_agent_service.list_sales_messages")
    def test_dry_run_summary_blocks_missing_eval(
        self,
        list_sales_messages,
        get_prospect,
        get_personalization,
        get_latest_eval_result,
    ) -> None:
        list_sales_messages.return_value = [self._message()]
        get_prospect.return_value = self._prospect()
        get_personalization.return_value = None
        get_latest_eval_result.return_value = None

        summary = SalesAgentService().dry_run_summary(2)

        self.assertEqual(summary.ready_count, 0)
        self.assertEqual(summary.blocked_count, 1)
        self.assertEqual(summary.items[0].eval_status, "missing")

    @patch("services.sales_agent_service.get_sales_agent")
    @patch("services.sales_agent_service.create_external_approval")
    @patch("services.sales_agent_service.SalesAgentService.dry_run_summary")
    def test_request_live_send_approval_includes_dry_run_summary(
        self,
        dry_run_summary,
        create_external_approval,
        get_sales_agent,
    ) -> None:
        get_sales_agent.return_value = type("Agent", (), {"id": 2})()
        dry_run_summary.return_value = type(
            "Summary",
            (),
            {
                "ready_count": 1,
                "blocked_count": 0,
                "items": [
                    type(
                        "Item",
                        (),
                        {
                            "message_id": 8,
                            "company_name": "Acme",
                            "subject": "Paid social idea for Acme",
                            "email_body": "Body",
                        },
                    )()
                ],
            },
        )()
        create_external_approval.return_value.model_dump.return_value = {"id": 1}

        result = SalesAgentService().request_first_live_send_approval(2)

        self.assertEqual(result, {"id": 1})
        request = create_external_approval.call_args.args[0]
        self.assertIn("exact first live", request.target_summary)
        self.assertIn("Ready messages: 1", request.target_summary)
        self.assertIn("Company: Acme", request.target_summary)
        self.assertIn("sales:first-live:2:message:8:", request.external_event_id)

    @patch("services.sales_agent_service.get_sales_agent")
    @patch("services.sales_agent_service.SalesAgentService.dry_run_summary")
    def test_request_live_send_approval_rejects_empty_batch(self, dry_run_summary, get_sales_agent) -> None:
        get_sales_agent.return_value = type("Agent", (), {"id": 2})()
        dry_run_summary.return_value = type("Summary", (), {"ready_count": 0, "blocked_count": 0, "items": []})()

        with self.assertRaises(ValueError):
            SalesAgentService().request_first_live_send_approval(2)

    @patch("services.sales_agent_service.create_sender_account")
    def test_create_sender_always_starts_paused_and_unverified(self, create_sender_account) -> None:
        create_sender_account.return_value.model_dump.return_value = {"id": 1, "status": "paused", "verified": False}

        result = SalesAgentService().create_sender(
            2,
            request=type("Request", (), {"email": "sender@example.com", "inbox_id": "inbox_1", "daily_cap": 5})(),
        )

        self.assertEqual(result["status"], "paused")
        self.assertEqual(create_sender_account.call_args.kwargs["status"], "paused")
        self.assertFalse(create_sender_account.call_args.kwargs["verified"])

    def test_personalize_rejects_unbounded_batch_size(self) -> None:
        with self.assertRaises(ValueError):
            SalesAgentService().personalize_prospects(2, limit=1000)

    @patch("services.sales_agent_service.create_outreach_message")
    @patch("services.sales_agent_service.record_eval_result")
    @patch("services.sales_agent_service.create_personalization")
    @patch("services.sales_agent_service.transition_prospect_status")
    @patch("services.sales_agent_service.list_sales_prospects")
    def test_personalize_creates_ready_to_send_message(
        self,
        list_sales_prospects,
        transition_prospect_status,
        create_personalization,
        record_eval_result,
        create_outreach_message,
    ) -> None:
        list_sales_prospects.return_value = [self._prospect()]
        create_personalization.return_value = Mock(id=9)
        client = Mock()
        client.create_strategy.return_value = GOOD_STRATEGY
        preview_service = Mock()
        preview_service.create_preview_token.return_value = ("preview-token", SalesPreviewToken(id=11, prospect_id=4, token_hash="h", purpose="preview"))
        preview_service.create_unsubscribe_token.return_value = ("unsubscribe-token", SalesPreviewToken(id=12, prospect_id=4, token_hash="h2", purpose="unsubscribe"))

        with patch.dict(
            os.environ,
            {
                "CONTROL_PUBLIC_BASE_URL": "https://sales.example.com",
                "SALES_UNSUBSCRIBE_BASE_URL": "https://sales.example.com",
                "TEMPA_DEMO_BOOKING_URL": "https://tempa.ai/demo",
                "SALES_POSTAL_ADDRESS": "1 Main St",
            },
            clear=False,
        ):
            result = SalesAgentService(personalization_client=client, preview_service=preview_service).personalize_prospects(2)

        self.assertEqual(result.personalized, 1)
        self.assertEqual(result.eval_failed, 0)
        create_outreach_message.assert_called_once()
        self.assertEqual(create_outreach_message.call_args.kwargs["status"], "ready_to_send")
        self.assertEqual(transition_prospect_status.call_count, 3)
        record_eval_result.assert_called_once()

    @patch("services.sales_agent_service.record_eval_result")
    @patch("services.sales_agent_service.create_personalization")
    @patch("services.sales_agent_service.transition_prospect_status")
    @patch("services.sales_agent_service.list_sales_prospects")
    def test_personalize_blocks_failed_eval(
        self,
        list_sales_prospects,
        transition_prospect_status,
        create_personalization,
        record_eval_result,
    ) -> None:
        list_sales_prospects.return_value = [self._prospect()]
        create_personalization.return_value = Mock(id=9)
        client = Mock()
        bad_strategy = dict(GOOD_STRATEGY)
        bad_strategy["evidence_urls"] = []
        client.create_strategy.return_value = bad_strategy
        preview_service = Mock()
        preview_service.create_preview_token.return_value = ("preview-token", SalesPreviewToken(id=11, prospect_id=4, token_hash="h", purpose="preview"))
        preview_service.create_unsubscribe_token.return_value = ("unsubscribe-token", SalesPreviewToken(id=12, prospect_id=4, token_hash="h2", purpose="unsubscribe"))

        with patch.dict(
            os.environ,
            {
                "CONTROL_PUBLIC_BASE_URL": "https://sales.example.com",
                "SALES_UNSUBSCRIBE_BASE_URL": "https://sales.example.com",
                "TEMPA_DEMO_BOOKING_URL": "https://tempa.ai/demo",
                "SALES_POSTAL_ADDRESS": "1 Main St",
            },
            clear=False,
        ):
            result = SalesAgentService(personalization_client=client, preview_service=preview_service).personalize_prospects(2)

        self.assertEqual(result.personalized, 0)
        self.assertEqual(result.eval_failed, 1)
        record_eval_result.assert_called_once()


if __name__ == "__main__":
    unittest.main()
