"""Regression tests for implementation prompt shaping and story flow helpers."""

import unittest

from implement import (
    _all_stories_completed,
    _build_claude_prompt,
    _fallback_story_from_research,
    _find_manual_review_story,
    _format_timeout,
    _select_next_story,
    _verification_failed,
    _verification_requires_manual_review,
)
from models.task import Task


class ImplementTimeoutTests(unittest.TestCase):
    def test_formats_minutes_cleanly(self) -> None:
        self.assertEqual(_format_timeout(300), "5 minutes")

    def test_formats_seconds_cleanly(self) -> None:
        self.assertEqual(_format_timeout(45), "45 seconds")

    def test_prompt_includes_execution_story_details(self) -> None:
        task = Task(
            title="Add planning loop",
            description="Use story-sized execution slices",
            category="ops",
            target_repo="studio/control-plane",
        )
        prompt = _build_claude_prompt(
            task,
            {
                "approach": ["Extend research output"],
                "files_to_modify": ["research.py"],
                "files_to_create": [],
                "risks": ["Prompt and code drift"],
                "execution_stories": [
                    {
                        "title": "Shape research output",
                        "priority": 1,
                        "summary": "Return small stories",
                        "acceptance_criteria": ["Stories include acceptance criteria"],
                        "verification": ["Run unit tests"],
                        "suggested_files": ["research.py", "prompts/research.md"],
                    }
                ],
            },
        )

        self.assertIn("Execution Stories", prompt)
        self.assertIn("Selected Story For This Run", prompt)
        self.assertIn("Shape research output", prompt)
        self.assertIn("Verify: Run unit tests", prompt)
        self.assertIn("File: research.py", prompt)

    def test_select_next_story_prefers_in_progress_then_pending(self) -> None:
        story = _select_next_story(
            [
                {"id": "STORY-2", "priority": 2, "status": "pending"},
                {"id": "STORY-1", "priority": 1, "status": "in_progress"},
            ]
        )

        self.assertEqual(story["id"], "STORY-1")

    def test_fallback_story_uses_approach_when_research_has_no_stories(self) -> None:
        stories = _fallback_story_from_research(
            {
                "summary": "Patch routing",
                "approach": ["Inspect router", "Add guardrail"],
                "files_to_modify": ["research.py"],
                "files_to_create": [],
            }
        )

        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0]["title"], "Implement approved plan")
        self.assertEqual(stories[0]["acceptance_criteria"], ["Inspect router", "Add guardrail"])

    def test_verification_failed_detects_failed_result(self) -> None:
        self.assertTrue(_verification_failed([{"status": "failed"}]))
        self.assertFalse(_verification_failed([{"status": "passed"}, {"status": "manual_required"}]))

    def test_manual_review_blocks_progress(self) -> None:
        self.assertTrue(_verification_requires_manual_review([{"status": "manual_required"}]))
        self.assertFalse(_verification_requires_manual_review([{"status": "passed"}]))

    def test_find_manual_review_story_returns_blocking_story(self) -> None:
        story = _find_manual_review_story(
            [
                {"id": "STORY-2", "priority": 2, "status": "pending"},
                {"id": "STORY-1", "priority": 1, "status": "awaiting_manual_verification"},
            ]
        )

        self.assertEqual(story["id"], "STORY-1")

    def test_all_stories_completed_requires_all_completed(self) -> None:
        self.assertTrue(_all_stories_completed([{"status": "completed"}]))
        self.assertFalse(
            _all_stories_completed(
                [{"status": "completed"}, {"status": "awaiting_manual_verification"}]
            )
        )


if __name__ == "__main__":
    unittest.main()
