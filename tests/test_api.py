"""Tests for the internal control-plane HTTP API."""

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app
from models.control_plane import ApprovalRequest, AttentionItem, Signal


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patcher = patch.dict(os.environ, {"CONTROL_API_TOKEN": "test-token"}, clear=False)
        self.env_patcher.start()
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-token"}

    def tearDown(self) -> None:
        self.env_patcher.stop()

    @patch("api.app.record_signal")
    def test_create_signal_endpoint_returns_signal_and_attention_item(self, record_signal) -> None:
        record_signal.return_value = {
            "signal": Signal(
                id=1,
                source="policy",
                kind="approval_required",
                severity="high",
                summary="Push requires approval",
                dedupe_key="abc123",
                bucket="approval_required",
            ),
            "attention_item": AttentionItem(
                id=2,
                signal_id=1,
                bucket="approval_required",
                severity="high",
                headline="Push requires approval",
                recommended_action="Approve or deny it.",
            ),
            "deduped": False,
        }

        response = self.client.post(
            "/v1/signals",
            json={
                "source": "policy",
                "kind": "approval_required",
                "severity": "high",
                "summary": "Push requires approval",
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["signal"]["kind"], "approval_required")
        self.assertEqual(response.json()["attention_item"]["bucket"], "approval_required")

    @patch("api.app.evaluate_and_record_policy")
    def test_policy_endpoint_returns_decision(self, evaluate_and_record_policy) -> None:
        evaluate_and_record_policy.return_value = type(
            "Result",
            (),
            {
                "model_dump": lambda self: {
                    "decision": "allow",
                    "policy_name": "default",
                    "reason": "ok",
                    "approval_required": False,
                    "policy_decision_id": 1,
                    "approval_request_id": None,
                    "signal_id": None,
                    "attention_item_id": None,
                }
            },
        )()

        response = self.client.post(
            "/v1/policy/evaluate",
            json={
                "task_id": 1,
                "agent_role": "implementer",
                "action_type": "read",
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "allow")

    @patch("api.app.resolve_approval")
    def test_resolve_approval_returns_forbidden_for_untrusted_users(self, resolve_approval) -> None:
        resolve_approval.side_effect = PermissionError("Slack user is not allowed to approve actions.")

        response = self.client.post(
            "/v1/approvals/12/resolve",
            json={
                "slack_user_id": "U123",
                "resolution": "approved",
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 403)

    @patch("api.app.create_approval")
    def test_create_approval_endpoint_returns_record(self, create_approval) -> None:
        create_approval.return_value = ApprovalRequest(
            id=3,
            task_id=9,
            action_type="git_push",
            target_summary="Push branch to repo",
        )

        response = self.client.post(
            "/v1/approvals",
            json={
                "task_id": 9,
                "action_type": "git_push",
                "target_summary": "Push branch to repo",
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["action_type"], "git_push")

    @patch("api.app.create_approval")
    def test_create_approval_endpoint_returns_bad_request_for_missing_task(self, create_approval) -> None:
        create_approval.side_effect = ValueError("Task 1 was not found.")

        response = self.client.post(
            "/v1/approvals",
            json={
                "task_id": 1,
                "action_type": "git_push",
                "target_summary": "Push branch to repo",
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Task 1 was not found.")

    @patch("api.app.Thread")
    @patch("api.app._worker_run_lock")
    def test_run_worker_once_endpoint_starts_background_pass(self, worker_run_lock, thread_cls) -> None:
        worker_run_lock.acquire.return_value = True

        response = self.client.post(
            "/v1/worker/run-once",
            json={"worker_id": "studio-chief"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "started")
        thread_cls.return_value.start.assert_called_once()

    @patch("api.app._worker_run_lock")
    def test_run_worker_once_endpoint_reports_when_pass_is_already_running(self, worker_run_lock) -> None:
        worker_run_lock.acquire.return_value = False

        response = self.client.post(
            "/v1/worker/run-once",
            json={"worker_id": "studio-chief"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "already_running")

    def test_control_api_requires_bearer_token(self) -> None:
        response = self.client.get("/v1/attention")

        self.assertEqual(response.status_code, 401)

    def test_control_api_rejects_wrong_bearer_token(self) -> None:
        response = self.client.get("/v1/attention", headers={"Authorization": "Bearer wrong"})

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
