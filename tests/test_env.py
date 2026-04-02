"""Regression tests for project environment loading."""

import os
from pathlib import Path
import tempfile
import unittest

from config.env import load_project_env


class ProjectEnvLoadingTests(unittest.TestCase):
    def test_project_env_overrides_stale_inherited_token(self) -> None:
        previous = os.environ.get("GITHUB_TOKEN")
        try:
            os.environ["GITHUB_TOKEN"] = "stale-token"
            with tempfile.TemporaryDirectory() as temp_dir:
                env_path = Path(temp_dir) / ".env"
                env_path.write_text("GITHUB_TOKEN=fresh-token\n")
                load_project_env(env_path)
            self.assertNotEqual(os.environ.get("GITHUB_TOKEN"), "stale-token")
            self.assertEqual(os.environ.get("GITHUB_TOKEN"), "fresh-token")
        finally:
            if previous is None:
                os.environ.pop("GITHUB_TOKEN", None)
            else:
                os.environ["GITHUB_TOKEN"] = previous


if __name__ == "__main__":
    unittest.main()
