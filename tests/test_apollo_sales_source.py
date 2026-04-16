"""Tests for Apollo prospect sourcing."""

import unittest
from unittest.mock import Mock, patch

from services.apollo_sales_source import (
    APOLLO_PEOPLE_SEARCH_URL,
    ApolloMissingApiKeyError,
    ApolloRateLimitError,
    ApolloSalesSource,
    ApolloSearchRequest,
    score_apollo_lead,
)


class ApolloSalesSourceTests(unittest.TestCase):
    def test_search_requires_api_key(self) -> None:
        with self.assertRaises(ApolloMissingApiKeyError):
            ApolloSalesSource(api_key="").search_people(ApolloSearchRequest())

    @patch("services.apollo_sales_source.httpx.post")
    def test_search_uses_people_api_search_endpoint_and_clamps_batch_size(self, post) -> None:
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"people": [{"id": "person_1"}]}
        response.raise_for_status.return_value = None
        post.return_value = response

        people = ApolloSalesSource(api_key="key").search_people(ApolloSearchRequest(per_page=100))

        self.assertEqual(people, [{"id": "person_1"}])
        self.assertEqual(post.call_args.args[0], APOLLO_PEOPLE_SEARCH_URL)
        self.assertEqual(post.call_args.kwargs["headers"]["x-api-key"], "key")
        self.assertEqual(post.call_args.kwargs["params"]["per_page"], 25)
        self.assertNotIn("min_signal_score", post.call_args.kwargs["params"])

    @patch("services.apollo_sales_source.httpx.post")
    def test_search_raises_rate_limit_error(self, post) -> None:
        response = Mock()
        response.status_code = 429
        post.return_value = response

        with self.assertRaises(ApolloRateLimitError):
            ApolloSalesSource(api_key="key").search_people(ApolloSearchRequest())

    def test_score_apollo_lead_explains_signals_and_warnings(self) -> None:
        signal = score_apollo_lead(
            {
                "email": "",
                "title": "Founder",
                "organization": {
                    "name": "Acme",
                    "primary_domain": "acme.com",
                    "estimated_num_employees": 25,
                    "keywords": ["growth", "software"],
                },
            },
            signal_keywords=["growth", "paid social"],
        )

        self.assertGreaterEqual(signal.score, 70)
        self.assertEqual(signal.tier, "high")
        self.assertIn("senior founder/operator title", signal.reasons)
        self.assertIn("missing email", signal.warnings)


if __name__ == "__main__":
    unittest.main()
