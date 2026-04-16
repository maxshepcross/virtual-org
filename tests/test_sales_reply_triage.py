"""Tests for sales reply triage."""

import unittest

from services.sales_reply_triage import SalesReplyTriage


class SalesReplyTriageTests(unittest.TestCase):
    def test_positive_reply(self) -> None:
        result = SalesReplyTriage().classify("Interested, can we book a demo next week?")
        self.assertEqual(result.classification, "positive")

    def test_unsubscribe_reply(self) -> None:
        result = SalesReplyTriage().classify("Please remove me from this list")
        self.assertEqual(result.classification, "unsubscribe")

    def test_empty_reply_is_unknown(self) -> None:
        result = SalesReplyTriage().classify("")
        self.assertEqual(result.classification, "unknown")


if __name__ == "__main__":
    unittest.main()
