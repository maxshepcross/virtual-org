#!/usr/bin/env python3
"""Run the studio worker loop that processes queued tasks from the control plane."""

from __future__ import annotations

import argparse
import json
import os
from uuid import uuid4

from config.env import load_project_env
from services.task_runner import TaskRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the AI Venture Studio worker loop.")
    parser.add_argument(
        "--worker-id",
        default=os.getenv("WORKER_ID") or f"worker-{uuid4().hex[:8]}",
        help="Stable worker identifier for leases and logs.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one available task, then exit.",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Stop after this many claimed tasks.",
    )
    parser.add_argument(
        "--idle-sleep-seconds",
        type=int,
        default=int(os.getenv("WORKER_IDLE_SLEEP_SECONDS", "5")),
        help="How long to sleep between queue polls when no task is available.",
    )
    return parser.parse_args()


def main() -> None:
    load_project_env()
    args = parse_args()
    runner = TaskRunner(
        worker_id=args.worker_id,
        poll_interval_seconds=args.idle_sleep_seconds,
    )
    if args.once:
        result = runner.run_once()
        print(json.dumps(result.__dict__, indent=2))
        return

    processed = runner.run_forever(max_tasks=args.max_tasks)
    print(json.dumps({"processed_tasks": processed}, indent=2))


if __name__ == "__main__":
    main()
