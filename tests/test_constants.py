"""Regression tests for queue timing defaults."""

import importlib
import os
import unittest
from unittest.mock import patch


class TimingDefaultsTests(unittest.TestCase):
    def test_default_lease_exceeds_implementation_timeout(self) -> None:
        with patch.dict(
            os.environ,
            {
                "IMPLEMENT_TIMEOUT_SECONDS": "900",
            },
            clear=False,
        ):
            import config.constants as constants

            reloaded = importlib.reload(constants)
            self.assertEqual(reloaded.IMPLEMENT_TIMEOUT_SECONDS, 900)
            self.assertEqual(reloaded.DEFAULT_LEASE_SECONDS, 1020)
            self.assertEqual(reloaded.LEASE_SECONDS, 1020)


if __name__ == "__main__":
    unittest.main()
