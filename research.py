"""Research agent — investigates ideas, assesses feasibility, produces implementation plans."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

import anthropic

from config.constants import RESEARCH_MODEL, MAX_RESEARCH_TOKENS, ALLOWED_REPOS
from config.env import load_project_env
from models.task import Task

load_project_env()
logger = logging.getLogger(__name__)

RESEARCH_PROMPT = (Path(__file__).parent / "prompts" / "research.md").read_text()

# Where repos are cloned locally for research
REPOS_DIR = Path(__file__).parent / ".repos"


def _coerce_prompt_value(value: Any) -> str:
    """Normalize prompt values so string replacement never crashes."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value if item is not None)
    if isinstance(value, dict):
        return json.dumps(value, indent=2, sort_keys=True)
    return str(value)


def _ensure_repo(repo: str) -> Path:
    """Clone or pull the target repo for research."""
    REPOS_DIR.mkdir(exist_ok=True)
    repo_dir = REPOS_DIR / repo.replace("/", "_")

    if repo_dir.exists():
        # Pull latest
        subprocess.run(
            ["git", "pull", "--rebase", "origin", "main"],
            cwd=repo_dir,
            capture_output=True,
            timeout=60,
        )
    else:
        # Clone
        subprocess.run(
            ["git", "clone", f"https://github.com/{repo}.git", str(repo_dir)],
            capture_output=True,
            timeout=120,
        )

    return repo_dir


def _search_codebase(repo_dir: Path, keywords: list[str], max_results: int = 20) -> str:
    """Search the repo for relevant code snippets."""
    results = []
    for keyword in keywords[:5]:  # Limit to 5 keywords
        try:
            proc = subprocess.run(
                ["grep", "-rn", "--include=*.py", "-l", keyword, "."],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.stdout.strip():
                files = proc.stdout.strip().split("\n")[:5]
                results.append(f"Files matching '{keyword}': {', '.join(files)}")
        except Exception:
            pass

    return "\n".join(results) if results else "No relevant files found."


def run_research(task: Task) -> dict:
    """Research a task and return structured findings."""
    client = anthropic.Anthropic()

    # Build context
    triage_sketch: Any = ""
    if task.idea_id:
        from models.idea import _conn
        import psycopg2.extras
        conn = _conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT triage_json FROM ideas WHERE id = %s", (task.idea_id,))
                row = cur.fetchone()
                if row and row["triage_json"]:
                    tj = row["triage_json"] if isinstance(row["triage_json"], dict) else json.loads(row["triage_json"])
                    triage_sketch = tj.get("approach_sketch", "")
        finally:
            conn.close()

    # Search codebase if it's a code task
    codebase_context = ""
    if task.target_repo and task.target_repo in ALLOWED_REPOS:
        try:
            repo_dir = _ensure_repo(task.target_repo)
            # Extract keywords from title and description
            keywords = [w for w in (task.title + " " + task.description).split() if len(w) > 4][:5]
            codebase_context = _search_codebase(repo_dir, keywords)
        except Exception as e:
            logger.warning("Could not search codebase: %s", e)
            codebase_context = f"Codebase search unavailable: {e}"

    prompt = RESEARCH_PROMPT.replace("{title}", _coerce_prompt_value(task.title))
    prompt = prompt.replace("{category}", _coerce_prompt_value(task.category))
    prompt = prompt.replace("{description}", _coerce_prompt_value(task.description))
    prompt = prompt.replace("{target_repo}", _coerce_prompt_value(task.target_repo or "N/A"))
    prompt = prompt.replace(
        "{approach_sketch}",
        _coerce_prompt_value(triage_sketch) or "None provided",
    )

    if codebase_context:
        prompt += f"\n\n## Codebase search results\n\n{codebase_context}"

    response = client.messages.create(
        model=RESEARCH_MODEL,
        max_tokens=MAX_RESEARCH_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    return json.loads(text.strip())
