"""Tests for public sales preview rendering."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from models.sales import SalesPersonalization, SalesPreviewToken, SalesProspect
from services.sales_preview_service import SalesPreviewService


class SalesPreviewServiceTests(unittest.TestCase):
    def _token(self) -> SalesPreviewToken:
        return SalesPreviewToken(
            id=3,
            prospect_id=9,
            token_hash="hash",
            purpose="preview",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )

    def _prospect(self) -> SalesProspect:
        return SalesProspect(
            id=9,
            agent_id=2,
            source="manual_seed",
            email="ada@example.com",
            normalized_email_hash="email-hash",
            first_name="Ada",
            company_name="Acme <script>",
            company_domain="acme.com",
        )

    def _personalization(self) -> SalesPersonalization:
        return SalesPersonalization(
            id=4,
            prospect_id=9,
            email_subject="Paid social idea for Acme",
            email_body="Body",
            strategy_json={
                "evidence_urls": ["https://example.com/acme", "http://not-allowed.test"],
                "observed_growth_context": "A new launch <b>stood out</b>",
                "suggested_paid_social_angle": "Founder-led demo",
                "target_audience": "Seed-stage founders",
                "example_ad_concept": "30-second walkthrough",
                "why_tempa_can_help": "Fast creative testing",
                "confidence_score": 0.91,
            },
        )

    @patch("services.sales_preview_service.get_latest_personalization_for_prospect")
    @patch("services.sales_preview_service.get_prospect")
    @patch("services.sales_preview_service.get_preview_token")
    def test_resolve_preview_renders_real_strategy_content(
        self,
        get_preview_token,
        get_prospect,
        get_latest_personalization_for_prospect,
    ) -> None:
        get_preview_token.return_value = self._token()
        get_prospect.return_value = self._prospect()
        get_latest_personalization_for_prospect.return_value = self._personalization()

        status, html = SalesPreviewService().resolve_preview("raw-token")

        self.assertEqual(status, "valid")
        self.assertIn("Paid social idea for Acme", html)
        self.assertIn("Founder-led demo", html)
        self.assertIn("Seed-stage founders", html)
        self.assertIn("https://example.com/acme", html)
        self.assertNotIn("http://not-allowed.test", html)

    @patch("services.sales_preview_service.get_latest_personalization_for_prospect")
    @patch("services.sales_preview_service.get_prospect")
    @patch("services.sales_preview_service.get_preview_token")
    def test_resolve_preview_escapes_strategy_html(
        self,
        get_preview_token,
        get_prospect,
        get_latest_personalization_for_prospect,
    ) -> None:
        get_preview_token.return_value = self._token()
        get_prospect.return_value = self._prospect()
        get_latest_personalization_for_prospect.return_value = self._personalization()

        _, html = SalesPreviewService().resolve_preview("raw-token")

        self.assertIn("Acme &lt;script&gt;", html)
        self.assertIn("A new launch &lt;b&gt;stood out&lt;/b&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>stood out</b>", html)

    @patch("services.sales_preview_service.get_latest_personalization_for_prospect")
    @patch("services.sales_preview_service.get_prospect")
    @patch("services.sales_preview_service.get_preview_token")
    def test_resolve_preview_fails_closed_without_personalization(
        self,
        get_preview_token,
        get_prospect,
        get_latest_personalization_for_prospect,
    ) -> None:
        get_preview_token.return_value = self._token()
        get_prospect.return_value = self._prospect()
        get_latest_personalization_for_prospect.return_value = None

        status, html = SalesPreviewService().resolve_preview("raw-token")

        self.assertEqual(status, "error")
        self.assertIn("Page not found", html)

    @patch("services.sales_preview_service.transition_prospect_status")
    @patch("services.sales_preview_service.record_suppression")
    @patch("services.sales_preview_service.mark_unsent_messages_for_prospect_status")
    @patch("services.sales_preview_service.get_prospect")
    @patch("services.sales_preview_service.get_preview_token")
    def test_unsubscribe_skips_unsent_messages(
        self,
        get_preview_token,
        get_prospect,
        mark_unsent_messages_for_prospect_status,
        record_suppression,
        transition_prospect_status,
    ) -> None:
        token = self._token()
        token.purpose = "unsubscribe"
        get_preview_token.return_value = token
        get_prospect.return_value = self._prospect()

        result = SalesPreviewService().unsubscribe("raw-token")

        self.assertTrue(result)
        record_suppression.assert_called_once()
        mark_unsent_messages_for_prospect_status.assert_called_once_with(9, "skipped")
        transition_prospect_status.assert_called_once()


if __name__ == "__main__":
    unittest.main()
