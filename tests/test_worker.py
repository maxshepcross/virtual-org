"""Regression tests for worker implementation result handling."""

import unittest
from unittest.mock import patch

from models.task import Task
from worker import _finalize_implementation_result


class WorkerImplementationResultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = Task(
            id=99,
            idea_id=12,
            title="Fix profile save",
            description="Bug fix",
            category="paperclip-bug",
            target_repo="maxshepcross/paperclip",
            lease_token="lease-123",
        )

    @patch("worker.notify_task_failed")
    @patch("worker.update_task_status")
    def test_error_result_marks_task_failed(self, update_task_status, notify_task_failed) -> None:
        update_task_status.return_value = self.task

        _finalize_implementation_result(
            self.task,
            {
                "branch_name": "paperclip/test-branch",
                "error": "Claude Code timed out after 5 minutes",
            },
            "C123",
            "123.456",
        )

        update_task_status.assert_called_once_with(
            99,
            "lease-123",
            "failed",
            event_message="Implementation failed: Claude Code timed out after 5 minutes",
            implementation_json={
                "branch_name": "paperclip/test-branch",
                "error": "Claude Code timed out after 5 minutes",
            },
            branch_name="paperclip/test-branch",
            error_message="Claude Code timed out after 5 minutes",
        )
        notify_task_failed.assert_called_once_with(
            "C123",
            "123.456",
            "Fix profile save",
            "Claude Code timed out after 5 minutes",
        )

    @patch("worker.notify_pr_opened")
    @patch("worker.update_task_status")
    def test_pr_result_marks_task_open(self, update_task_status, notify_pr_opened) -> None:
        update_task_status.return_value = self.task

        _finalize_implementation_result(
            self.task,
            {
                "branch_name": "paperclip/test-branch",
                "pr_url": "https://github.com/maxshepcross/paperclip/pull/1",
                "pr_number": 1,
            },
            "C123",
            "123.456",
        )

        update_task_status.assert_called_once_with(
            99,
            "lease-123",
            "pr_open",
            event_message="PR opened: https://github.com/maxshepcross/paperclip/pull/1",
            implementation_json={
                "branch_name": "paperclip/test-branch",
                "pr_url": "https://github.com/maxshepcross/paperclip/pull/1",
                "pr_number": 1,
            },
            pr_url="https://github.com/maxshepcross/paperclip/pull/1",
            pr_number=1,
            pr_status="open",
            branch_name="paperclip/test-branch",
        )
        notify_pr_opened.assert_called_once_with(
            "C123",
            "123.456",
            "Fix profile save",
            "https://github.com/maxshepcross/paperclip/pull/1",
            "maxshepcross/paperclip",
            1,
        )
