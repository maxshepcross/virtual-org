"""Regression tests for task model JSON field handling and manual review helpers."""

import unittest
from unittest.mock import patch

from models.task import _row_to_task, complete_manual_verification, get_active_tasks


class TaskModelJsonFieldTests(unittest.TestCase):
    def test_row_to_task_parses_story_and_progress_json_fields(self) -> None:
        task = _row_to_task(
            {
                "id": 1,
                "title": "Shape execution state",
                "description": "Track stories explicitly",
                "category": "ops",
                "status": "queued",
                "execution_stories_json": '[{"id": "STORY-1", "status": "pending"}]',
                "progress_notes_json": '[{"message": "Started"}]',
                "verification_json": '[{"story_id": "STORY-1"}]',
                "events": "[]",
            }
        )

        self.assertEqual(task.execution_stories_json[0]["id"], "STORY-1")
        self.assertEqual(task.progress_notes_json[0]["message"], "Started")
        self.assertEqual(task.verification_json[0]["story_id"], "STORY-1")

    @patch("models.task._conn")
    def test_get_active_tasks_excludes_pr_open(self, conn_factory) -> None:
        conn = conn_factory.return_value
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []

        get_active_tasks()

        self.assertIn("WHERE status NOT IN %s", cursor.execute.call_args.args[0])
        self.assertEqual(cursor.execute.call_args.args[1], (("pr_open", "done", "failed"),))

    @patch("models.task._conn")
    def test_complete_manual_verification_marks_story_completed(self, conn_factory) -> None:
        conn = conn_factory.return_value
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [
            {
                "id": 7,
                "title": "Review story",
                "description": "Wait for human check",
                "category": "ops",
                "status": "implementing",
                "execution_stories_json": [
                    {"id": "STORY-1", "title": "Ship fix", "priority": 1, "status": "awaiting_manual_verification"},
                    {"id": "STORY-2", "title": "Next step", "priority": 2, "status": "pending"},
                ],
                "progress_notes_json": [],
                "verification_json": [],
                "events": [],
            },
            {
                "id": 7,
                "title": "Review story",
                "description": "Wait for human check",
                "category": "ops",
                "status": "queued",
                "execution_stories_json": '[{"id":"STORY-1","title":"Ship fix","priority":1,"status":"completed"},{"id":"STORY-2","title":"Next step","priority":2,"status":"pending"}]',
                "progress_notes_json": '[{"message":"Checked in browser"}]',
                "verification_json": '[{"story_id":"STORY-1"}]',
                "current_story_id": "STORY-2",
                "events": "[]",
            },
        ]

        task = complete_manual_verification(7, note="Checked in browser")

        self.assertEqual(task.execution_stories_json[0]["status"], "completed")
        self.assertEqual(task.status, "queued")
        self.assertEqual(task.current_story_id, "STORY-2")


if __name__ == "__main__":
    unittest.main()
