#!/usr/bin/env python3
"""Run the internal control API with the project environment loaded."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    uvicorn.run(
        "api.app:app",
        host=os.getenv("CONTROL_API_HOST", "127.0.0.1"),
        port=int(os.getenv("CONTROL_API_PORT", "8080")),
        reload=False,
    )


if __name__ == "__main__":
    main()
