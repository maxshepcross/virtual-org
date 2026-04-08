"""Tests for the deterministic Slack dispatcher service."""

import unittest
from unittest.mock import patch

from models.control_plane import ApprovalRequest, AttentionItem
from services.slack_dispatcher import _format_approval_request, _format_attention_item, dispatch_once


class SlackDispatcherTests(unittest.TestCase):
    def test_format_attention_item_includes_key_fields(self) -> None:
        item = AttentionItem(
            id=1,
            task_id=7,
            bucket="notify",
            severity="high",
            headline="Manual smoke test",
            recommended_action="Review the issue.",
        )

        text = _format_attention_item(item)

        self.assertIn("[HIGH] Manual smoke test", text)
        self.assertIn("Task: 7", text)
        self.assertIn("Recommended action: Review the issue.", text)

    def test_format_approval_request_includes_approval_id(self) -> None:
        request = ApprovalRequest(
            id=5,
            task_id=9,
            action_type="git_push",
            target_summary="Push branch to repo",
        )

        text = _format_approval_request(request)

        self.assertIn("Approval ID: 5", text)
        self.assertIn("Target: Push branch to repo", text)

    @patch("services.slack_dispatcher.update_task_slack_route")
    @patch("services.slack_dispatcher.get_task")
    @patch("services.slack_dispatcher.mark_approval_request_posted")
    @patch("services.slack_dispatcher.mark_attention_item_posted")
    @patch("services.slack_dispatcher.list_unposted_approval_requests")
    @patch("services.slack_dispatcher.list_unposted_attention_items")
    @patch("services.slack_dispatcher.SlackClient")
    @patch("services.slack_dispatcher.load_project_env")
    @patch("services.slack_dispatcher.os.getenv")
    def test_dispatch_once_posts_attention_and_approval_items(
        self,
        getenv,
        _load_project_env,
        slack_client_cls,
        list_attention,
        list_approvals,
        mark_attention_posted,
        mark_approval_posted,
        get_task,
        update_task_route,
    ) -> None:
        getenv.side_effect = lambda key, default=None: {
            "SLACK_BOT_TOKEN": "xoxb-test",
            "SLACK_DISPATCH_INTERVAL_SECONDS": "10",
        }.get(key, default)
        list_attention.return_value = [
            AttentionItem(
                id=1,
                task_id=7,
                bucket="notify",
                severity="high",
                headline="Manual smoke test",
                recommended_action="Review it.",
                slack_channel_id="#virtual-org-chief",
            )
        ]
        list_approvals.return_value = [
            ApprovalRequest(
                id=2,
                task_id=7,
                action_type="git_push",
                target_summary="Push branch",
                requested_slack_channel_id="#virtual-org-chief",
            )
        ]
        slack_client = slack_client_cls.return_value
        get_task.side_effect = [
            type("TaskStub", (), {"slack_thread_ts": None})(),
            type("TaskStub", (), {"slack_thread_ts": "111.222"})(),
        ]
        slack_client.post_message.side_effect = [
            type("SlackResult", (), {"channel": "C123", "ts": "111.222"})(),
            type("SlackResult", (), {"channel": "C123", "ts": "111.333"})(),
        ]

        result = dispatch_once()

        self.assertEqual(result["attention_items_sent"], 1)
        self.assertEqual(result["approval_requests_sent"], 1)
        mark_attention_posted.assert_called_once_with(1, slack_message_ts="111.222")
        mark_approval_posted.assert_called_once_with(2, slack_message_ts="111.333")
        update_task_route.assert_called_once_with(7, slack_channel_id="C123", slack_thread_ts="111.222")


if __name__ == "__main__":
    unittest.main()
