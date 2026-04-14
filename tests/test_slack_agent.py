"""Tests for Slack agent verification and founder command handling."""

import unittest
from unittest.mock import patch

from models.control_plane import ApprovalRequest, AttentionItem
from models.task import Task
from services.slack_agent import (
    _run_command,
    handle_interactivity,
    parse_interactivity_payload,
    verify_slack_signature,
)


class SlackAgentTests(unittest.TestCase):
    def test_verify_slack_signature_accepts_valid_request(self) -> None:
        body = b'{"type":"event_callback"}'
        timestamp = "1710000000"
        secret = "signing-secret"
        import hashlib
        import hmac

        signature = "v0=" + hmac.new(
            secret.encode("utf-8"),
            f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        verify_slack_signature(
            timestamp=timestamp,
            signature=signature,
            body=body,
            signing_secret=secret,
            now=1710000001,
        )

    def test_parse_interactivity_payload_rejects_bad_json(self) -> None:
        with self.assertRaises(RuntimeError):
            parse_interactivity_payload("{bad-json")

    @patch("services.slack_agent.list_attention_items")
    @patch("services.slack_agent.get_pending_approvals")
    def test_run_command_reports_blocked_items(self, get_pending_approvals, list_attention_items) -> None:
        get_pending_approvals.return_value = [
            ApprovalRequest(id=4, task_id=9, action_type="git_push", target_summary="Push the branch"),
        ]
        list_attention_items.return_value = [
            AttentionItem(
                id=7,
                task_id=9,
                bucket="notify",
                severity="high",
                headline="Task failed",
                recommended_action="Review it.",
            )
        ]

        result = _run_command("what is blocked", slack_user_id="U123")

        self.assertIn("Pending approvals:", result.text)
        self.assertIn("High-priority alerts:", result.text)

    @patch("services.slack_agent.get_task_control_state")
    def test_run_command_formats_task_summary(self, get_task_control_state) -> None:
        get_task_control_state.return_value = {
            "task": Task(id=12, title="Fix bug", description="...", category="ops", status="awaiting_approval"),
            "approval_requests": [],
            "attention_items": [],
            "policy_decisions": [],
            "agent_runs": [],
        }

        result = _run_command("task 12", slack_user_id="U123")

        self.assertIn("Task 12: Fix bug", result.text)
        self.assertIn("Status: awaiting_approval", result.text)

    @patch("services.slack_agent.SlackApiClient")
    @patch("services.slack_agent.get_approval_request")
    @patch("services.slack_agent.resolve_approval")
    def test_handle_interactivity_updates_message_after_resolution(
        self,
        resolve_approval,
        get_approval_request,
        slack_api_client_cls,
    ) -> None:
        resolve_approval.return_value = ApprovalRequest(
            id=5,
            task_id=22,
            action_type="git_push",
            target_summary="Push branch",
            status="approved",
        )
        get_approval_request.return_value = ApprovalRequest(
            id=5,
            task_id=22,
            action_type="git_push",
            target_summary="Push branch",
            status="approved",
        )

        response = handle_interactivity(
            {
                "user": {"id": "U123"},
                "channel": {"id": "C123"},
                "message": {"ts": "111.222"},
                "actions": [{"action_id": "approval_approve", "value": "5:approved"}],
            }
        )

        self.assertEqual(response["replace_original"], False)
        self.assertIn("Approval #5 approved", response["text"])
        slack_api_client_cls.return_value.update_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
