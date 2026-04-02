"""Shared environment loading for the Virtual Org app."""

from pathlib import Path
from typing import Union

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def load_project_env(env_path: Union[str, Path, None] = None) -> None:
    """Load the project .env file and override any stale inherited values."""
    load_dotenv(env_path or ENV_PATH, override=True)
