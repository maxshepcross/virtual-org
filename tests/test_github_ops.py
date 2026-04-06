"""Regression tests for git branch setup helpers."""

import unittest
from pathlib import Path
from unittest.mock import patch

from services.github_ops import create_branch


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


if __name__ == "__main__":
    unittest.main()
