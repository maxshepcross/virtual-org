"""Tests for the control-plane policy engine."""

import unittest
from unittest.mock import patch

from services.policy_engine import PolicyEvaluationRequest, evaluate_policy


class PolicyEngineTests(unittest.TestCase):
    @patch("services.policy_engine.ALLOWED_REPOS", ["studio/control"])
    def test_blocks_disallowed_repo_targets(self) -> None:
        result = evaluate_policy(
            PolicyEvaluationRequest(
                task_id=1,
                agent_role="implementer",
                action_type="git_push",
                target_repo="other/repo",
            )
        )

        self.assertEqual(result.decision, "block")
        self.assertEqual(result.policy_name, "repo-allowlist")

    def test_blocks_mutating_actions_for_researcher(self) -> None:
        result = evaluate_policy(
            PolicyEvaluationRequest(
                task_id=1,
                agent_role="researcher",
                action_type="file_write",
            )
        )

        self.assertEqual(result.decision, "block")
        self.assertEqual(result.policy_name, "role-boundary")

    def test_requires_approval_for_github_network_access(self) -> None:
        result = evaluate_policy(
            PolicyEvaluationRequest(
                task_id=1,
                agent_role="implementer",
                action_type="network_request",
                target_host="github.com",
            )
        )

        self.assertEqual(result.decision, "require_approval")
        self.assertTrue(result.approval_required)

    def test_blocks_unknown_network_hosts_by_default(self) -> None:
        result = evaluate_policy(
            PolicyEvaluationRequest(
                task_id=1,
                agent_role="implementer",
                action_type="network_request",
                target_host="evil.example.com",
            )
        )

        self.assertEqual(result.decision, "block")
        self.assertEqual(result.policy_name, "network-default-deny")

    def test_allows_read_only_action(self) -> None:
        result = evaluate_policy(
            PolicyEvaluationRequest(
                task_id=1,
                agent_role="reviewer",
                action_type="read",
            )
        )

        self.assertEqual(result.decision, "allow")


if __name__ == "__main__":
    unittest.main()
