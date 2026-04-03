"""Regression tests for git branch setup helpers."""

import unittest
from pathlib import Path
from unittest.mock import patch

from services.github_ops import create_branch


class CreateBranchTests(unittest.TestCase):
    @patch("services.github_ops._run_git")
    def test_create_branch_cleans_stale_branch_before_recreating(self, run_git) -> None:
        run_git.side_effect = [
            None,  # checkout main
            None,  # fetch origin main
            None,  # reset hard origin/main
            None,  # clean -fd
            type("Result", (), {"stdout": "  paperclip/idea-2-fix-save\n"})(),
            None,  # delete existing branch
            None,  # checkout -b new branch
        ]

        branch = create_branch(Path("/tmp/repo"), 2, "Fix save")

        self.assertEqual(branch, "paperclip/idea-2-fix-save")
        self.assertEqual(
            [call.args[1] for call in run_git.call_args_list],
            [
                ["checkout", "main"],
                ["fetch", "origin", "main"],
                ["reset", "--hard", "origin/main"],
                ["clean", "-fd"],
                ["branch", "--list", "paperclip/idea-2-fix-save"],
                ["branch", "-D", "paperclip/idea-2-fix-save"],
                ["checkout", "-b", "paperclip/idea-2-fix-save"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
