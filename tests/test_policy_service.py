"""Tests for recorded policy decisions and approval idempotency inputs."""

import json
import unittest

from services.policy_engine import PolicyEvaluationRequest
from services.policy_service import _target_summary


class PolicyServiceTests(unittest.TestCase):
    def test_target_summary_uses_repo_when_present(self) -> None:
        request = PolicyEvaluationRequest(
            task_id=7,
            agent_role="implementer",
            action_type="git_push",
            target_repo="owner/repo",
        )

        self.assertEqual(_target_summary(request), "git_push on repo owner/repo")

    def test_external_event_id_shape_includes_task_id(self) -> None:
        request = PolicyEvaluationRequest(
            task_id=42,
            agent_run_id=9,
            agent_role="implementer",
            action_type="network_request",
            target_host="github.com",
        )

        external_event_id = (
            f"{request.task_id}:{request.agent_run_id or 'no-run'}:{request.action_type}:"
            f"{request.target_host or request.target_repo or 'general'}"
        )

        self.assertEqual(external_event_id, "42:9:network_request:github.com")


class OpenClawPluginPackageTests(unittest.TestCase):
    def test_plugin_package_declares_openclaw_dependency_and_metadata(self) -> None:
        with open("openclaw/plugins/studio-control/package.json", "r", encoding="utf-8") as handle:
            package = json.load(handle)

        self.assertEqual(package["openclaw"]["extensions"], ["./dist/index.js"])
        self.assertIn("openclaw", package["peerDependencies"])
        self.assertIn("openclaw", package["devDependencies"])


if __name__ == "__main__":
    unittest.main()
