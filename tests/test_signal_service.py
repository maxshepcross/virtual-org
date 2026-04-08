"""Tests for signal bucketing and dedupe-key generation."""

import unittest

from services.signal_service import SignalInput, build_dedupe_key, classify_signal


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


if __name__ == "__main__":
    unittest.main()
