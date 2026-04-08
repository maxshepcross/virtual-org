#!/usr/bin/env python3
"""Run the Slack dispatcher loop that posts alerts and approvals to Slack."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.slack_dispatcher import run_forever


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()
