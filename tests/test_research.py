"""Regression tests for research prompt building."""

import unittest

from research import RESEARCH_PROMPT, _coerce_prompt_value


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


if __name__ == "__main__":
    unittest.main()
