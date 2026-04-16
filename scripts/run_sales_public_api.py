#!/usr/bin/env python3
"""Run the public sales app for preview, unsubscribe, and webhooks."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.env import load_project_env


def main() -> None:
    load_project_env()
    host = os.getenv("SALES_PUBLIC_API_HOST", "127.0.0.1")
    port = int(os.getenv("SALES_PUBLIC_API_PORT", "8091"))
    uvicorn.run("api.sales_public_app:app", host=host, port=port)


if __name__ == "__main__":
    main()
