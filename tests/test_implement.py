"""Regression tests for implementation prompt shaping and story flow helpers."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

_IMPORTED_ENV_KEYS = (
    "CONTROL_API_TOKEN",
    "DATABASE_URL",
    "GITHUB_TOKEN",
    "IMPLEMENT_TIMEOUT_SECONDS",
    "LEASE_SECONDS",
)
_ENV_BEFORE_IMPLEMENT_IMPORT = {key: os.environ.get(key) for key in _IMPORTED_ENV_KEYS}

from implement import (
    _all_stories_completed,
    _build_claude_command,
    _build_claude_prompt,
    _fallback_story_from_research,
    _find_manual_review_story,
    _format_timeout,
    _looks_like_permission_error,
    _select_next_story,
    _verification_failed,
    _verification_requires_manual_review,
    run_implementation,
)
from models.control_plane import AgentRun
from models.task import Task

for _key, _value in _ENV_BEFORE_IMPLEMENT_IMPORT.items():
    if _value is None:
        os.environ.pop(_key, None)
    else:
        os.environ[_key] = _value


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

    def test_claude_command_uses_safer_permission_mode(self) -> None:
        command = _build_claude_command("Ship the selected story", Path("/tmp/example"))

        self.assertIn("--permission-mode", command)
        self.assertIn("acceptEdits", command)
        self.assertNotIn("--dangerously-skip-permissions", command)

    def test_permission_error_detection_handles_common_messages(self) -> None:
        self.assertTrue(_looks_like_permission_error("Permission denied for Bash tool"))
        self.assertFalse(_looks_like_permission_error("Process exited with code 1"))

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

    @patch("implement.append_agent_run_artifact")
    @patch("implement.update_agent_run")
    @patch("implement.update_task_status")
    @patch("implement.ensure_branch")
    @patch("implement.create_agent_run")
    def test_run_implementation_marks_run_failed_when_branch_setup_raises(
        self,
        create_agent_run,
        ensure_branch,
        update_task_status,
        update_agent_run,
        append_agent_run_artifact,
    ) -> None:
        create_agent_run.return_value = AgentRun(
            id=41,
            task_id=7,
            run_key="run-41",
            story_id="STORY-1",
            run_kind="implementation",
            trigger_source="task_queue",
            agent_class="claude",
            agent_role="implementer",
            status="running",
        )
        ensure_branch.side_effect = RuntimeError("dirty repo")

        with TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "owner_repo").mkdir()
            task = Task(
                id=7,
                title="Ship fix",
                description="Implement the first story",
                category="ops",
                target_repo="owner/repo",
                lease_token="lease-1",
                approval_state="approved",
            )

            with patch("implement.REPOS_DIR", repo_root), patch("implement.ALLOWED_REPOS", ["owner/repo"]):
                result = run_implementation(
                    task,
                    {
                        "execution_stories": [
                            {
                                "id": "STORY-1",
                                "title": "Fix branch flow",
                                "priority": 1,
                                "status": "pending",
                                "verification": [],
                            }
                        ]
                    },
                )

        self.assertEqual(result["run_id"], 41)
        self.assertEqual(result["run_key"], "run-41")
        self.assertEqual(result["current_story_id"], "STORY-1")
        self.assertIn("dirty repo", result["error"])
        append_agent_run_artifact.assert_called_with(
            41,
            {
                "type": "run_error",
                "at": append_agent_run_artifact.call_args.args[1]["at"],
                "story_id": "STORY-1",
                "error": "dirty repo",
            },
        )
        update_agent_run.assert_called_with(
            41,
            "failed",
            completed_by="implement.py",
            branch_name=None,
            pr_url=None,
            error_message="dirty repo",
        )
        update_task_status.assert_called_once()
        self.assertEqual(update_task_status.call_args.args[:3], (7, "lease-1", "failed"))


if __name__ == "__main__":
    unittest.main()
