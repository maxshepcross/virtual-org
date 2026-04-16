"""Tests for internal sales API routes."""

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from services.apollo_sales_source import ApolloMissingApiKeyError, ApolloRateLimitError


class SalesApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from api.app import app

        cls.app = app

    def setUp(self) -> None:
        self.env_patcher = patch.dict(os.environ, {"CONTROL_API_TOKEN": "test-token"}, clear=False)
        self.env_patcher.start()
        self.client = TestClient(self.app)
        self.headers = {"Authorization": "Bearer test-token"}

    def tearDown(self) -> None:
        self.env_patcher.stop()

    @patch("api.app._sales_service")
    def test_create_sales_agent_requires_auth_and_returns_agent(self, service) -> None:
        service.create_agent.return_value.model_dump.return_value = {"id": 1, "venture": "tempa"}

        response = self.client.post(
            "/v1/sales/agents",
            json={"name": "Tempa Sales Agent"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["venture"], "tempa")
        service.create_agent.assert_called_once_with(name="Tempa Sales Agent", venture="tempa")

    def test_sales_agent_route_rejects_missing_auth(self) -> None:
        response = self.client.get("/v1/sales/agents")
        self.assertEqual(response.status_code, 401)

    @patch("api.app._sales_service")
    def test_sales_health_uses_service(self, service) -> None:
        service.health.return_value = {"kill_switch": True, "send_mode": "dry_run", "agents": []}

        response = self.client.get("/v1/sales/health", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["kill_switch"])

    @patch("api.app._sales_service")
    def test_personalize_sales_prospects_returns_counts(self, service) -> None:
        service.personalize_prospects.return_value.model_dump.return_value = {
            "personalized": 1,
            "eval_failed": 0,
            "failed": 0,
        }

        response = self.client.post(
            "/v1/sales/agents/3/personalize",
            json={"limit": 5},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["personalized"], 1)
        service.personalize_prospects.assert_called_once_with(3, limit=5)

    @patch("api.app._sales_service")
    def test_create_sales_sender_endpoint(self, service) -> None:
        service.create_sender.return_value = {"id": 4, "email": "sender@example.com", "verified": False}

        response = self.client.post(
            "/v1/sales/agents/3/senders",
            json={
                "email": "sender@example.com",
                "inbox_id": "inbox_123",
                "daily_cap": 5,
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["email"], "sender@example.com")
        self.assertEqual(service.create_sender.call_args.args[0], 3)

    @patch("api.app._sales_service")
    def test_create_sales_sender_rejects_direct_verified_status(self, service) -> None:
        response = self.client.post(
            "/v1/sales/agents/3/senders",
            json={
                "email": "sender@example.com",
                "inbox_id": "inbox_123",
                "status": "active",
                "verified": True,
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 422)
        service.create_sender.assert_not_called()

    @patch("api.app._sales_service")
    def test_personalize_sales_prospects_rejects_large_limit(self, service) -> None:
        response = self.client.post(
            "/v1/sales/agents/3/personalize",
            json={"limit": 1000},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 422)
        service.personalize_prospects.assert_not_called()

    @patch("api.app._sales_service")
    def test_set_sales_agent_send_mode_endpoint(self, service) -> None:
        service.set_send_mode.return_value.model_dump.return_value = {
            "id": 3,
            "send_mode": "live",
        }

        response = self.client.post(
            "/v1/sales/agents/3/send-mode",
            json={"send_mode": "live"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["send_mode"], "live")
        service.set_send_mode.assert_called_once_with(3, "live")

    @patch("api.app._sales_service")
    def test_request_live_approval_endpoint(self, service) -> None:
        service.request_first_live_send_approval.return_value = {
            "id": 9,
            "action_type": "sales_first_live_send",
            "status": "pending",
        }

        response = self.client.post(
            "/v1/sales/agents/3/request-live-approval",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["action_type"], "sales_first_live_send")
        service.request_first_live_send_approval.assert_called_once_with(3)

    @patch("api.app._sales_service")
    def test_dry_run_summary_endpoint(self, service) -> None:
        service.dry_run_summary.return_value.model_dump.return_value = {
            "agent_id": 3,
            "ready_count": 1,
            "blocked_count": 0,
            "items": [{"company_name": "Acme"}],
        }

        response = self.client.get(
            "/v1/sales/agents/3/dry-run-summary?limit=10",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ready_count"], 1)
        service.dry_run_summary.assert_called_once_with(3, limit=10)

    @patch("api.app._sales_service")
    def test_import_sales_prospects_returns_400_for_missing_apollo_key(self, service) -> None:
        service.import_prospects.side_effect = ApolloMissingApiKeyError("APOLLO_API_KEY is not configured.")

        response = self.client.post(
            "/v1/sales/agents/3/import",
            json={"source": "apollo", "apollo_search": {"per_page": 5}},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("APOLLO_API_KEY", response.json()["detail"])

    @patch("api.app._sales_service")
    def test_import_sales_prospects_returns_429_for_apollo_rate_limit(self, service) -> None:
        service.import_prospects.side_effect = ApolloRateLimitError("Apollo rate limit reached.")

        response = self.client.post(
            "/v1/sales/agents/3/import",
            json={"source": "apollo", "apollo_search": {"per_page": 5}},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 429)


if __name__ == "__main__":
    unittest.main()
