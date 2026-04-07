#!/usr/bin/env python3
"""Mark a manually reviewed execution story as complete."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.env import load_project_env
from models.task import complete_manual_verification


def main() -> int:
    load_project_env()

    parser = argparse.ArgumentParser(
        description="Mark a story waiting on manual verification as complete.",
    )
    parser.add_argument("task_id", type=int, help="Task ID to update")
    parser.add_argument("--story-id", help="Optional story ID if more than one is blocked")
    parser.add_argument(
        "--note",
        default="Manual verification completed.",
        help="Short note explaining what was checked",
    )
    args = parser.parse_args()

    task = complete_manual_verification(
        task_id=args.task_id,
        story_id=args.story_id,
        note=args.note,
    )
    print(f"Task {task.id} updated.")
    print(f"Current status: {task.status}")
    print(f"Next story: {task.current_story_id or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
