"""Tests for approval-service authorization and race-safe behavior."""

import unittest
from unittest.mock import patch

from models.control_plane import ApprovalRequest
from services.approval_service import ApprovalResolutionRequest, resolve_approval


class ApprovalServiceTests(unittest.TestCase):
    @patch("services.approval_service.get_approval_request")
    @patch("services.approval_service.resolve_approval_request")
    @patch("services.approval_service.os.getenv")
    def test_resolve_returns_existing_resolution_when_race_already_resolved(
        self,
        getenv,
        resolve_approval_request,
        get_approval_request,
    ) -> None:
        getenv.return_value = "U123"
        get_approval_request.return_value = ApprovalRequest(
            id=5,
            task_id=7,
            action_type="git_push",
            target_summary="Push branch",
            status="pending",
        )
        resolve_approval_request.return_value = ApprovalRequest(
            id=5,
            task_id=7,
            action_type="git_push",
            target_summary="Push branch",
            status="approved",
            approved_by_slack_user_id="U123",
        )

        result = resolve_approval(
            5,
            ApprovalResolutionRequest(
                slack_user_id="U123",
                resolution="approved",
            ),
        )

        self.assertEqual(result.status, "approved")

    @patch("services.approval_service.get_approval_request")
    @patch("services.approval_service.os.getenv")
    def test_resolve_rejects_untrusted_user(self, getenv, get_approval_request) -> None:
        getenv.return_value = "U123"
        get_approval_request.return_value = ApprovalRequest(
            id=6,
            task_id=8,
            action_type="git_push",
            target_summary="Push branch",
            status="pending",
        )

        with self.assertRaises(PermissionError):
            resolve_approval(
                6,
                ApprovalResolutionRequest(
                    slack_user_id="U999",
                    resolution="approved",
                ),
            )


if __name__ == "__main__":
    unittest.main()
