#!/usr/bin/env python3
"""Run the internal control API with the project environment loaded."""

from __future__ import annotations

import os

import uvicorn

from config.env import load_project_env


def main() -> None:
    load_project_env()
    uvicorn.run(
        "api.app:app",
        host=os.getenv("CONTROL_API_HOST", "127.0.0.1"),
        port=int(os.getenv("CONTROL_API_PORT", "8080")),
        reload=False,
    )


if __name__ == "__main__":
    main()
