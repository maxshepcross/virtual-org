"""Tests for Tempa sales personalization eval gates."""

import json
import unittest
from pathlib import Path

from services.sales_eval_service import SalesEvalInput, SalesEvalService


GOOD_STRATEGY = {
    "company": "Acme",
    "prospect": "Ada",
    "evidence_urls": ["https://example.com"],
    "observed_growth_context": "new product launch",
    "suggested_paid_social_angle": "founder-led proof",
    "target_audience": "startup founders",
    "example_ad_concept": "short demo clip",
    "why_tempa_can_help": "fast ad testing",
    "confidence_score": 0.91,
}


class SalesEvalServiceTests(unittest.TestCase):
    def test_passes_valid_strategy_and_email(self) -> None:
        result = SalesEvalService().evaluate(
            SalesEvalInput(
                strategy_json=GOOD_STRATEGY,
                email_subject="Paid social idea for Acme",
                email_body="Hello\nUnsubscribe: https://example.com/u",
                postal_address="1 Main St",
                unsubscribe_link="https://example.com/u",
            )
        )

        self.assertTrue(result.passed)
        self.assertIsNone(result.llm_passed)
        self.assertEqual(result.failures, [])

    def test_blocks_missing_evidence_and_unsubscribe(self) -> None:
        bad_strategy = dict(GOOD_STRATEGY)
        bad_strategy["evidence_urls"] = []

        result = SalesEvalService().evaluate(
            SalesEvalInput(
                strategy_json=bad_strategy,
                email_subject="Paid social idea for Acme",
                email_body="Hello",
                postal_address="1 Main St",
            )
        )

        self.assertFalse(result.passed)
        self.assertIn("missing evidence_urls", result.failures)
        self.assertIn("unsubscribe link is required", result.failures)

    def test_fixed_eval_fixture_suite(self) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "sales_eval_cases.json"
        cases = json.loads(fixture_path.read_text())
        self.assertEqual(len(cases), 20)

        service = SalesEvalService()
        for case in cases:
            with self.subTest(case=case["name"]):
                result = service.evaluate(
                    SalesEvalInput(
                        strategy_json=case["strategy"],
                        email_subject=case["subject"],
                        email_body=case["body"],
                        postal_address=case.get("postal_address", "1 Main St") or None,
                        unsubscribe_link=case.get("unsubscribe_link", "https://example.com/u"),
                    )
                )
                self.assertEqual(result.passed, case["expected_pass"])


if __name__ == "__main__":
    unittest.main()
