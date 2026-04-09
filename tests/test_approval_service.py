"""Tests for approval-service authorization and race-safe behavior."""

import unittest
from unittest.mock import patch

from models.control_plane import ApprovalRequest
from models.task import Task
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

    @patch("services.approval_service.get_approval_request")
    @patch("services.approval_service.resolve_approval_request")
    @patch("services.approval_service.os.getenv")
    def test_resolve_allows_any_slack_user_when_wildcard_is_configured(
        self,
        getenv,
        resolve_approval_request,
        get_approval_request,
    ) -> None:
        getenv.return_value = "*"
        get_approval_request.return_value = ApprovalRequest(
            id=7,
            task_id=8,
            action_type="git_push",
            target_summary="Push branch",
            status="pending",
        )
        resolve_approval_request.return_value = ApprovalRequest(
            id=7,
            task_id=8,
            action_type="git_push",
            target_summary="Push branch",
            status="approved",
            approved_by_slack_user_id="U999",
        )

        result = resolve_approval(
            7,
            ApprovalResolutionRequest(
                slack_user_id="U999",
                resolution="approved",
            ),
        )

        self.assertEqual(result.status, "approved")

    @patch("services.approval_service.create_approval_request")
    @patch("services.approval_service.get_task")
    @patch("services.slack_routing.get_task")
    @patch("services.slack_routing.os.getenv")
    def test_create_approval_uses_task_slack_route(
        self,
        getenv,
        get_route_task,
        get_task,
        create_approval_request,
    ) -> None:
        from services.approval_service import ApprovalCreateRequest, create_approval

        getenv.return_value = "#default-chief"
        get_task.return_value = Task(
            id=9,
            title="Test",
            description="Test",
            category="ops",
        )
        get_route_task.return_value = Task(
            id=9,
            title="Test",
            description="Test",
            category="ops",
            slack_channel_id="#task-channel",
            slack_thread_ts="111.222",
        )
        create_approval_request.return_value = ApprovalRequest(
            id=9,
            task_id=9,
            action_type="git_push",
            target_summary="Push branch",
            requested_slack_channel_id="#task-channel",
            requested_slack_thread_ts="111.222",
        )

        create_approval(
            ApprovalCreateRequest(
                task_id=9,
                action_type="git_push",
                target_summary="Push branch",
            )
        )

        _, kwargs = create_approval_request.call_args
        self.assertEqual(kwargs["requested_slack_channel_id"], "#task-channel")
        self.assertEqual(kwargs["requested_slack_thread_ts"], "111.222")


if __name__ == "__main__":
    unittest.main()
