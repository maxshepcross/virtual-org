"""Regression tests for implementation timeout handling."""

import unittest

from implement import _format_timeout


class ImplementTimeoutTests(unittest.TestCase):
    def test_formats_minutes_cleanly(self) -> None:
        self.assertEqual(_format_timeout(300), "5 minutes")

    def test_formats_seconds_cleanly(self) -> None:
        self.assertEqual(_format_timeout(45), "45 seconds")


if __name__ == "__main__":
    unittest.main()
