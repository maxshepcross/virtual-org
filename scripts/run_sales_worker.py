#!/usr/bin/env python3
"""Run the dedicated sales worker for a sales agent."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.env import load_project_env
from services.sales_send_worker import SalesSendWorker


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Tempa sales worker.")
    parser.add_argument("agent_id", type=int, nargs="?")
    parser.add_argument("--loop", action="store_true", help="Keep polling instead of running one pass.")
    parser.add_argument("--poll-interval-seconds", type=int, default=60)
    parser.add_argument("--max-passes", type=int)
    parser.add_argument("--stop-on-blocked", action="store_true")
    args = parser.parse_args()

    load_project_env()
    agent_id = args.agent_id
    if agent_id is None:
        raw_agent_id = os.getenv("SALES_AGENT_ID", "").strip()
        if not raw_agent_id:
            parser.error("agent_id is required, either as an argument or SALES_AGENT_ID in the environment.")
        try:
            agent_id = int(raw_agent_id)
        except ValueError:
            parser.error("SALES_AGENT_ID must be an integer.")
    worker = SalesSendWorker()
    if args.loop:
        result = worker.run_loop(
            agent_id,
            poll_interval_seconds=args.poll_interval_seconds,
            max_passes=args.max_passes,
            stop_on_blocked=args.stop_on_blocked,
        )
    else:
        result = worker.run_once(agent_id)
    print(result.model_dump_json())


if __name__ == "__main__":
    main()
