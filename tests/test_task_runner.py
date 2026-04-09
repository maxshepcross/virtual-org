"""Regression tests for the single-process task runner loop."""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

from models.task import Task
from services.task_runner import TaskRunner


def build_task(**overrides) -> Task:
    base = {
        "id": 7,
        "title": "Run worker loop",
        "description": "Keep tasks moving",
        "category": "ops",
        "status": "claimed",
        "lease_token": "lease-123",
        "current_story_id": "STORY-1",
    }
    base.update(overrides)
    return Task(**base)


class TaskRunnerLoopTests(unittest.TestCase):
    @patch("services.task_runner.claim_next_task")
    @patch("services.task_runner.fail_stale_tasks")
    def test_run_once_returns_idle_when_queue_is_empty(self, fail_stale_tasks_mock, claim_next_task_mock) -> None:
        fail_stale_tasks_mock.return_value = []
        claim_next_task_mock.return_value = None

        result = TaskRunner(worker_id="worker-a").run_once()

        self.assertEqual(result.action, "idle")
        self.assertIn("No queued tasks", result.message)

    @patch("services.task_runner.run_implementation")
    @patch("services.task_runner.run_research")
    @patch("services.task_runner.get_task")
    @patch("services.task_runner.update_task_status")
    @patch("services.task_runner.claim_next_task")
    @patch("services.task_runner.fail_stale_tasks")
    def test_run_once_researches_then_implements_unplanned_task(
        self,
        fail_stale_tasks_mock,
        claim_next_task_mock,
        update_task_status_mock,
        get_task_mock,
        run_research_mock,
        run_implementation_mock,
    ) -> None:
        claimed = build_task()
        researching = build_task(status="researching")
        implementing = build_task(
            status="implementing",
            research_json={"summary": "Planned"},
            execution_stories_json=[{"id": "STORY-1", "status": "pending"}],
        )
        done = build_task(
            status="pr_open",
            research_json={"summary": "Planned"},
            execution_stories_json=[{"id": "STORY-1", "status": "completed"}],
        )

        fail_stale_tasks_mock.return_value = []
        claim_next_task_mock.return_value = claimed
        update_task_status_mock.side_effect = [researching, implementing]
        run_research_mock.return_value = {"summary": "Planned"}
        run_implementation_mock.return_value = {"pr_url": "https://example.com/pr/1"}
        get_task_mock.side_effect = [implementing, done]

        result = TaskRunner(worker_id="worker-a", heartbeat_interval_seconds=1).run_once()

        self.assertEqual(result.action, "completed")
        self.assertEqual(result.task_status, "pr_open")
        run_research_mock.assert_called_once()
        run_implementation_mock.assert_called_once()

    @patch("services.task_runner.run_implementation")
    @patch("services.task_runner.get_task")
    @patch("services.task_runner.update_task_status")
    @patch("services.task_runner.claim_next_task")
    @patch("services.task_runner.fail_stale_tasks")
    def test_run_once_waits_for_manual_verification_when_implementation_requests_it(
        self,
        fail_stale_tasks_mock,
        claim_next_task_mock,
        update_task_status_mock,
        get_task_mock,
        run_implementation_mock,
    ) -> None:
        claimed = build_task(
            research_json={"summary": "Planned"},
            execution_stories_json=[{"id": "STORY-1", "status": "pending"}],
        )
        blocked = build_task(
            status="blocked",
            research_json={"summary": "Planned"},
            execution_stories_json=[{"id": "STORY-1", "status": "awaiting_manual_verification"}],
        )

        fail_stale_tasks_mock.return_value = []
        claim_next_task_mock.return_value = claimed
        update_task_status_mock.return_value = claimed
        run_implementation_mock.return_value = {"manual_verification_required": True}
        get_task_mock.return_value = blocked

        result = TaskRunner(worker_id="worker-a").run_once()

        self.assertEqual(result.action, "awaiting_manual_verification")
        self.assertEqual(result.task_status, "blocked")

    @patch("services.task_runner.run_implementation")
    @patch("services.task_runner.get_task")
    @patch("services.task_runner.update_task_status")
    @patch("services.task_runner.claim_next_task")
    @patch("services.task_runner.fail_stale_tasks")
    def test_run_once_requeues_task_when_more_stories_remain(
        self,
        fail_stale_tasks_mock,
        claim_next_task_mock,
        update_task_status_mock,
        get_task_mock,
        run_implementation_mock,
    ) -> None:
        claimed = build_task(
            research_json={"summary": "Planned"},
            execution_stories_json=[
                {"id": "STORY-1", "status": "completed"},
                {"id": "STORY-2", "status": "pending"},
            ],
            current_story_id="STORY-2",
        )
        implementing = build_task(
            status="implementing",
            research_json={"summary": "Planned"},
            execution_stories_json=[
                {"id": "STORY-1", "status": "completed"},
                {"id": "STORY-2", "status": "pending"},
            ],
            current_story_id="STORY-2",
        )
        requeued = build_task(
            status="queued",
            research_json={"summary": "Planned"},
            execution_stories_json=[
                {"id": "STORY-1", "status": "completed"},
                {"id": "STORY-2", "status": "pending"},
            ],
            current_story_id="STORY-2",
        )

        fail_stale_tasks_mock.return_value = []
        claim_next_task_mock.return_value = claimed
        update_task_status_mock.return_value = implementing
        run_implementation_mock.return_value = {"next_story_id": "STORY-2"}
        get_task_mock.return_value = requeued

        result = TaskRunner(worker_id="worker-a").run_once()

        self.assertEqual(result.action, "progressed")
        self.assertEqual(result.task_status, "queued")

    @patch("services.task_runner.heartbeat_task")
    def test_run_with_heartbeat_renews_lease_while_long_step_runs(self, heartbeat_task_mock) -> None:
        runner = TaskRunner(heartbeat_interval_seconds=1)
        task = build_task()
        started = threading.Event()

        def slow_operation() -> str:
            started.set()
            time.sleep(1.2)
            return "done"

        result = runner._run_with_heartbeat(task, slow_operation)

        self.assertEqual(result, "done")
        self.assertTrue(started.is_set())
        heartbeat_task_mock.assert_called_with(task.id, task.lease_token)

    @patch("services.task_runner.update_task_status")
    @patch("services.task_runner.claim_next_task")
    @patch("services.task_runner.fail_stale_tasks")
    def test_run_once_marks_task_failed_when_runner_step_raises(
        self,
        fail_stale_tasks_mock,
        claim_next_task_mock,
        update_task_status_mock,
    ) -> None:
        claimed = build_task()
        failed = build_task(status="failed")

        fail_stale_tasks_mock.return_value = []
        claim_next_task_mock.return_value = claimed
        update_task_status_mock.side_effect = RuntimeError("boom"), failed

        runner = TaskRunner(worker_id="worker-a")
        runner._start_phase = unittest.mock.Mock(side_effect=RuntimeError("boom"))
        runner._mark_failed = unittest.mock.Mock(return_value=failed)

        result = runner.run_once()

        self.assertEqual(result.action, "failed")
        self.assertEqual(result.task_status, "failed")


if __name__ == "__main__":
    unittest.main()
