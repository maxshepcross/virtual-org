"""Regression tests for git branch setup and push helpers."""

import unittest
from pathlib import Path
from unittest.mock import patch

from services.github_ops import commit_and_push, create_branch, ensure_branch


class CreateBranchTests(unittest.TestCase):
    @patch("services.github_ops._run_git")
    def test_create_branch_starts_from_origin_main(self, run_git) -> None:
        run_git.side_effect = [
            None,  # fetch origin main
            type("Result", (), {"stdout": ""})(),
            None,  # checkout -B from origin/main
        ]

        branch = create_branch(Path("/tmp/repo"), 2, "Fix save")

        self.assertEqual(branch, "studio/task-2-fix-save")
        self.assertEqual(
            [call.args[1] for call in run_git.call_args_list],
            [
                ["fetch", "origin", "main"],
                ["status", "--porcelain"],
                ["checkout", "-B", "studio/task-2-fix-save", "origin/main"],
            ],
        )

    @patch("services.github_ops._run_git")
    def test_create_branch_refuses_dirty_repo(self, run_git) -> None:
        run_git.side_effect = [
            None,
            type("Result", (), {"stdout": " M app.py\n"})(),
        ]

        with self.assertRaises(RuntimeError):
            create_branch(Path("/tmp/repo"), 2, "Fix save")

    @patch("services.github_ops._run_git")
    def test_ensure_branch_reuses_existing_branch(self, run_git) -> None:
        run_git.side_effect = [
            None,  # fetch
            type("Result", (), {"stdout": ""})(),
            None,  # checkout existing branch
        ]

        branch = ensure_branch(Path("/tmp/repo"), 2, "Fix save", "studio/task-2-fix-save")

        self.assertEqual(branch, "studio/task-2-fix-save")
        self.assertEqual(
            [call.args[1] for call in run_git.call_args_list],
            [
                ["fetch", "origin", "main"],
                ["status", "--porcelain"],
                ["checkout", "studio/task-2-fix-save"],
            ],
        )

    @patch("services.github_ops.subprocess.run")
    def test_commit_and_push_reports_push_failure(self, run_subprocess) -> None:
        run_subprocess.side_effect = [
            type("Result", (), {"returncode": 0})(),  # git add
            type("Result", (), {"stdout": " M app.py\n", "returncode": 0})(),  # git status
            type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})(),  # git commit
            type("Result", (), {"returncode": 1, "stderr": "auth failed", "stdout": ""})(),  # git push
        ]

        result = commit_and_push(Path("/tmp/repo"), "studio/task-2-fix-save", "msg")

        self.assertEqual(result["status"], "push_failed")
        self.assertIn("auth failed", result["error"])


if __name__ == "__main__":
    unittest.main()
