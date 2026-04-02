"""Regression tests for triage task creation rules."""

import unittest
from unittest.mock import patch

from models.task import Task
from triage import _find_duplicate_task, _should_create_task


class TriageTaskCreationTests(unittest.TestCase):
    @patch("triage.get_latest_task_for_title")
    def test_failed_duplicate_is_retriable(self, get_latest_task_for_title) -> None:
        result = {
            "category": "tempa-feature",
            "duplicate_of": "Change dashboard page title to 'Tempa Dashboard'",
        }
        get_latest_task_for_title.return_value = Task(
            id=3,
            idea_id=4,
            title="Change dashboard page title to 'Tempa Dashboard'",
            description="Change the title",
            category="tempa-feature",
            status="failed",
        )

        self.assertTrue(_should_create_task(result))
        self.assertIsNone(result["duplicate_of"])

    @patch("triage.get_latest_task_for_title")
    def test_active_duplicate_stays_blocked(self, get_latest_task_for_title) -> None:
        result = {
            "category": "tempa-feature",
            "duplicate_of": "Change dashboard page title to 'Tempa Dashboard'",
        }
        get_latest_task_for_title.return_value = Task(
            id=4,
            idea_id=5,
            title="Change dashboard page title to 'Tempa Dashboard'",
            description="Change the title",
            category="tempa-feature",
            status="queued",
        )

        self.assertFalse(_should_create_task(result))
        self.assertEqual(
            result["duplicate_of"],
            "Change dashboard page title to 'Tempa Dashboard'",
        )

    @patch("triage.get_recent_tasks")
    @patch("triage.get_latest_task_for_title")
    def test_fuzzy_duplicate_finds_failed_retry(
        self,
        get_latest_task_for_title,
        get_recent_tasks,
    ) -> None:
        result = {
            "category": "tempa-feature",
            "target_repo": "maxshepcross/tempa",
            "title": "Change dashboard browser tab title to 'Tempa Dashboard'",
            "duplicate_of": "Change dashboard page title to 'Tempa Dashboard'",
        }
        get_latest_task_for_title.return_value = None
        get_recent_tasks.return_value = [
            Task(
                id=3,
                idea_id=4,
                title="Change dashboard page title to 'Tempa Dashboard'",
                description="Change the title",
                category="tempa-feature",
                target_repo="maxshepcross/tempa",
                status="failed",
            )
        ]

        task = _find_duplicate_task(result)

        self.assertIsNotNone(task)
        self.assertEqual(task.id, 3)

    @patch("triage.get_recent_tasks")
    @patch("triage.get_latest_task_for_title")
    def test_fuzzy_duplicate_keeps_active_task_blocked(
        self,
        get_latest_task_for_title,
        get_recent_tasks,
    ) -> None:
        result = {
            "category": "tempa-feature",
            "target_repo": "maxshepcross/tempa",
            "title": "Change dashboard browser tab title to 'Tempa Dashboard'",
            "duplicate_of": "Change dashboard page title to 'Tempa Dashboard'",
        }
        get_latest_task_for_title.return_value = None
        get_recent_tasks.return_value = [
            Task(
                id=4,
                idea_id=5,
                title="Change dashboard page title to 'Tempa Dashboard'",
                description="Change the title",
                category="tempa-feature",
                target_repo="maxshepcross/tempa",
                status="researching",
            )
        ]

        self.assertFalse(_should_create_task(result))


if __name__ == "__main__":
    unittest.main()
