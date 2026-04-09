"""Tests for signal bucketing and dedupe-key generation."""

import unittest
from unittest.mock import patch

from services.signal_service import SignalInput, build_dedupe_key, classify_signal
from models.task import Task


class SignalServiceTests(unittest.TestCase):
    def test_build_dedupe_key_is_stable_for_same_signal(self) -> None:
        signal = SignalInput(
            source="policy",
            kind="approval_required",
            task_id=7,
            severity="high",
            summary="Push requires approval",
        )

        self.assertEqual(build_dedupe_key(signal), build_dedupe_key(signal))

    def test_classify_signal_routes_approval_to_attention_queue(self) -> None:
        self.assertEqual(classify_signal("approval_required", "high"), "approval_required")

    def test_classify_signal_ignores_heartbeat_noise(self) -> None:
        self.assertEqual(classify_signal("heartbeat", "low"), "ignore")

    def test_classify_signal_notifies_on_critical_failures(self) -> None:
        self.assertEqual(classify_signal("task_failed", "critical"), "notify")

    def test_classify_signal_digests_normal_updates(self) -> None:
        self.assertEqual(classify_signal("story_completed", "normal"), "digest")

    @patch("services.signal_service.create_attention_item")
    @patch("services.signal_service.create_signal")
    @patch("services.signal_service.find_recent_signal_by_dedupe_key")
    @patch("services.slack_routing.get_task")
    @patch("services.slack_routing.os.getenv")
    def test_record_signal_uses_task_or_default_slack_route(
        self,
        getenv,
        get_task,
        find_recent,
        create_signal,
        create_attention_item,
    ) -> None:
        find_recent.return_value = None
        create_signal.return_value = type(
            "SignalStub",
            (),
            {
                "id": 1,
                "task_id": 7,
                "agent_run_id": 12,
                "venture": None,
                "severity": "high",
                "summary": "Manual test",
            },
        )()
        create_attention_item.return_value = object()
        get_task.return_value = Task(
            id=7,
            title="Test",
            description="Test",
            category="ops",
            slack_channel_id="#task-thread",
            slack_thread_ts="123.456",
        )
        getenv.return_value = "#default-chief"

        from services.signal_service import record_signal

        record_signal(
            SignalInput(
                source="manual",
                kind="smoke_test",
                task_id=7,
                severity="high",
                summary="Manual test",
            )
        )

        create_attention_item.assert_called_once()
        _, kwargs = create_attention_item.call_args
        self.assertEqual(kwargs["slack_channel_id"], "#task-thread")
        self.assertEqual(kwargs["slack_thread_ts"], "123.456")
        self.assertEqual(kwargs["agent_run_id"], 12)

    @patch("services.signal_service.create_attention_item")
    @patch("services.signal_service.create_signal")
    @patch("services.signal_service.find_recent_signal_by_dedupe_key")
    @patch("services.slack_routing.get_task")
    @patch("services.slack_routing.os.getenv")
    def test_record_signal_falls_back_to_default_slack_channel(
        self,
        getenv,
        get_task,
        find_recent,
        create_signal,
        create_attention_item,
    ) -> None:
        find_recent.return_value = None
        create_signal.return_value = type(
            "SignalStub",
            (),
            {
                "id": 1,
                "task_id": None,
                "agent_run_id": None,
                "venture": None,
                "severity": "high",
                "summary": "Manual test",
            },
        )()
        create_attention_item.return_value = object()
        get_task.return_value = None
        getenv.side_effect = lambda key: {
            "SLACK_DEFAULT_CHANNEL_ID": "#virtual-org-chief",
            "SLACK_DEFAULT_THREAD_TS": None,
        }.get(key)

        from services.signal_service import record_signal

        record_signal(
            SignalInput(
                source="manual",
                kind="smoke_test",
                severity="high",
                summary="Manual test",
            )
        )

        _, kwargs = create_attention_item.call_args
        self.assertEqual(kwargs["slack_channel_id"], "#virtual-org-chief")
        self.assertIsNone(kwargs["slack_thread_ts"])


if __name__ == "__main__":
    unittest.main()
