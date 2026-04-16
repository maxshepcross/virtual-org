"""Tests for Tempa personalization client safety checks."""

import os
import unittest
from unittest.mock import patch

from models.sales import SalesProspect
from services.sales_personalization import TempaPersonalizationClient


class TempaPersonalizationClientTests(unittest.TestCase):
    def _prospect(self) -> SalesProspect:
        return SalesProspect(
            id=4,
            agent_id=2,
            source="manual_seed",
            email="ada@example.com",
            normalized_email_hash="hash",
            company_name="Acme",
        )

    def test_strategy_url_must_be_https(self) -> None:
        client = TempaPersonalizationClient(url="http://tempa.example/strategy")

        with self.assertRaisesRegex(RuntimeError, "HTTPS"):
            client.create_strategy(self._prospect())

    @patch("services.sales_personalization.httpx.post")
    def test_strategy_url_host_allowlist(self, post) -> None:
        client = TempaPersonalizationClient(url="https://wrong.example/strategy")

        with patch.dict(os.environ, {"TEMPA_SALES_STRATEGY_ALLOWED_HOSTS": "tempa.example"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "not allowed"):
                client.create_strategy(self._prospect())

        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
