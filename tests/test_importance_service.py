"""Tests for the business-signal importance layer."""

import unittest
from unittest.mock import patch

from services.importance_service import BusinessSignalInput, evaluate_business_signal, record_business_signal


class ImportanceServiceTests(unittest.TestCase):
    def test_evaluate_business_signal_ignores_small_movements(self) -> None:
        decision = evaluate_business_signal(
            BusinessSignalInput(
                source="paperclip",
                category="usage",
                metric_name="weekly_active_users",
                summary="Usage is up 2% this week",
                direction="up",
                change_percent=2,
            )
        )

        self.assertFalse(decision.should_record)
        self.assertEqual(decision.bucket, "ignore")

    def test_evaluate_business_signal_routes_positive_trend_to_digest(self) -> None:
        decision = evaluate_business_signal(
            BusinessSignalInput(
                source="paperclip",
                category="usage",
                metric_name="weekly_active_users",
                summary="Usage is up 20% this week",
                direction="up",
                change_percent=20,
            )
        )

        self.assertTrue(decision.should_record)
        self.assertEqual(decision.bucket, "digest")
        self.assertEqual(decision.severity, "normal")

    def test_evaluate_business_signal_routes_revenue_drop_to_notify(self) -> None:
        decision = evaluate_business_signal(
            BusinessSignalInput(
                source="paperclip",
                category="revenue",
                metric_name="monthly_revenue",
                summary="Revenue is down 14% this month",
                direction="down",
                change_percent=-14,
            )
        )

        self.assertTrue(decision.should_record)
        self.assertEqual(decision.bucket, "notify")
        self.assertEqual(decision.severity, "high")

    @patch("services.importance_service.record_signal")
    def test_record_business_signal_passes_decision_into_signal_layer(self, record_signal_mock) -> None:
        record_signal_mock.return_value = {
            "signal": object(),
            "attention_item": object(),
            "deduped": False,
        }

        result = record_business_signal(
            BusinessSignalInput(
                source="paperclip",
                category="usage",
                metric_name="weekly_active_users",
                summary="Usage is up 20% this week",
                direction="up",
                change_percent=20,
            )
        )

        self.assertEqual(result["decision"]["bucket"], "digest")
        record_signal_mock.assert_called_once()
        signal_input = record_signal_mock.call_args.args[0]
        self.assertEqual(signal_input.freshness_seconds, 86_400)


if __name__ == "__main__":
    unittest.main()
