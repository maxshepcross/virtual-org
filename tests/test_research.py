"""Regression tests for research prompt building and result normalization."""

import unittest
from unittest.mock import patch

from models.task import Task
from research import (
    RESEARCH_PROMPT,
    _build_research_prompt,
    _coerce_prompt_value,
    _normalize_research_result,
    _normalize_task_breakdown_result,
)


class ResearchPromptValueTests(unittest.TestCase):
    def test_list_values_become_bullets(self) -> None:
        value = ["First step", "Second step"]

        self.assertEqual(
            _coerce_prompt_value(value),
            "- First step\n- Second step",
        )

    def test_prompt_accepts_list_approach_sketch(self) -> None:
        prompt = RESEARCH_PROMPT.replace(
            "{approach_sketch}",
            _coerce_prompt_value(["Find the bug", "Patch the handler"]),
        )

        self.assertIn("- Find the bug", prompt)
        self.assertIn("- Patch the handler", prompt)

    def test_research_prompt_includes_policy_context(self) -> None:
        task = Task(
            title="Fix task routing",
            description="Route tasks more safely",
            category="ops",
            target_repo=None,
        )

        with patch("research._load_prompt_context") as load_prompt_context:
            load_prompt_context.side_effect = [
                "Priority rules",
                "Auto rules",
                "Heartbeat rules",
            ]
            prompt = _build_research_prompt(task)

        self.assertIn("Priority rules", prompt)
        self.assertIn("Auto rules", prompt)
        self.assertIn("Heartbeat rules", prompt)
        self.assertIn("Fix task routing", prompt)

    def test_research_prompt_includes_prd_and_story_breakdown(self) -> None:
        task = Task(
            title="Fix task routing",
            description="Route tasks more safely",
            category="ops",
            target_repo=None,
        )

        with patch("research._load_prompt_context") as load_prompt_context:
            load_prompt_context.side_effect = [
                "Priority rules",
                "Auto rules",
                "Heartbeat rules",
            ]
            prompt = _build_research_prompt(
                task,
                prd_markdown="## Overview\nShape the work first.",
                task_breakdown={
                    "summary": "Break the work into slices",
                    "execution_stories": [{"id": "STORY-1", "title": "Draft PRD"}],
                },
            )

        self.assertIn("Draft PRD", prompt)
        self.assertIn("Break the work into slices", prompt)
        self.assertIn("STORY-1", prompt)

    def test_normalize_research_result_fills_story_defaults(self) -> None:
        result = _normalize_research_result(
            {
                "summary": "Looks good",
                "approach": "Inspect the routing logic",
                "execution_stories": [
                    {
                        "title": "Harden router",
                        "priority": "2",
                        "acceptance_criteria": "No unsafe repo guesses",
                    },
                    "Add tests",
                ],
            }
        )

        self.assertEqual(result["approach"], ["Inspect the routing logic"])
        self.assertEqual(len(result["execution_stories"]), 2)
        self.assertEqual(result["execution_stories"][0]["title"], "Harden router")
        self.assertEqual(
            result["execution_stories"][0]["acceptance_criteria"],
            ["No unsafe repo guesses"],
        )
        self.assertEqual(result["execution_stories"][0]["status"], "pending")
        self.assertEqual(result["execution_stories"][1]["title"], "Add tests")
        self.assertEqual(result["execution_stories"][1]["id"], "STORY-2")

    def test_task_breakdown_normalization_fills_story_defaults(self) -> None:
        result = _normalize_task_breakdown_result(
            {
                "summary": "Ship small slices",
                "execution_stories": [
                    {"title": "Story one", "priority": "3"},
                    "Story two",
                ],
            }
        )

        self.assertEqual(result["summary"], "Ship small slices")
        self.assertEqual(result["execution_stories"][0]["title"], "Story one")
        self.assertEqual(result["execution_stories"][0]["priority"], 3)
        self.assertEqual(result["execution_stories"][1]["id"], "STORY-2")


if __name__ == "__main__":
    unittest.main()
