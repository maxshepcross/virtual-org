"""Research helper for studio tasks and target repos."""

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
from models.task import Task, update_task_status

load_project_env()
logger = logging.getLogger(__name__)

RESEARCH_PROMPT = (Path(__file__).parent / "prompts" / "research.md").read_text()
CONFIG_DIR = Path(__file__).parent / "config"

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


def _load_prompt_context(filename: str) -> str:
    """Load optional markdown context for prompts from the config folder."""
    path = CONFIG_DIR / filename
    if not path.exists():
        return "Not configured."
    return path.read_text().strip()


def _normalize_string_list(value: Any) -> list[str]:
    """Normalize a field into a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _normalize_execution_story(index: int, story: Any) -> dict[str, Any]:
    """Coerce one execution story into the expected shape."""
    if not isinstance(story, dict):
        story = {"title": str(story)}

    priority = story.get("priority", index + 1)
    try:
        priority = int(priority)
    except (TypeError, ValueError):
        priority = index + 1

    return {
        "id": str(story.get("id") or f"STORY-{index + 1}"),
        "title": str(story.get("title") or f"Story {index + 1}"),
        "summary": str(story.get("summary") or ""),
        "priority": priority,
        "acceptance_criteria": _normalize_string_list(story.get("acceptance_criteria")),
        "verification": _normalize_string_list(story.get("verification")),
        "suggested_files": _normalize_string_list(story.get("suggested_files")),
        "status": str(story.get("status") or "pending"),
    }


def _normalize_research_result(result: dict[str, Any]) -> dict[str, Any]:
    """Make LLM output predictable for downstream code."""
    normalized = dict(result)
    normalized["summary"] = str(normalized.get("summary") or "")
    normalized["feasibility"] = str(normalized.get("feasibility") or "unclear")
    normalized["approach"] = _normalize_string_list(normalized.get("approach"))
    normalized["files_to_modify"] = _normalize_string_list(normalized.get("files_to_modify"))
    normalized["files_to_create"] = _normalize_string_list(normalized.get("files_to_create"))
    normalized["risks"] = _normalize_string_list(normalized.get("risks"))
    normalized["dependencies"] = _normalize_string_list(normalized.get("dependencies"))
    normalized["estimated_effort"] = str(normalized.get("estimated_effort") or "medium")
    normalized["recommendation"] = str(normalized.get("recommendation") or "needs_discussion")
    normalized["recommendation_reason"] = str(normalized.get("recommendation_reason") or "")

    raw_stories = normalized.get("execution_stories")
    if not isinstance(raw_stories, list):
        raw_stories = []
    normalized["execution_stories"] = [
        _normalize_execution_story(index, story)
        for index, story in enumerate(raw_stories)
    ]
    normalized["execution_stories"].sort(key=lambda story: (story["priority"], story["id"]))
    return normalized


def _build_research_prompt(task: Task, codebase_context: str = "") -> str:
    """Build the research prompt with studio policy context."""
    prompt = RESEARCH_PROMPT.replace("{title}", _coerce_prompt_value(task.title))
    prompt = prompt.replace("{category}", _coerce_prompt_value(task.category))
    prompt = prompt.replace("{description}", _coerce_prompt_value(task.description))
    prompt = prompt.replace("{target_repo}", _coerce_prompt_value(task.target_repo or "N/A"))
    prompt = prompt.replace("{approach_sketch}", _coerce_prompt_value("") or "None provided")
    prompt = prompt.replace("{priority_map}", _load_prompt_context("studio-priority-map.md"))
    prompt = prompt.replace(
        "{auto_resolution_policy}",
        _load_prompt_context("studio-auto-resolution.md"),
    )
    prompt = prompt.replace("{heartbeat}", _load_prompt_context("studio-heartbeat.md"))

    if codebase_context:
        prompt += f"\n\n## Codebase search results\n\n{codebase_context}"

    return prompt


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

    # Search the named codebase only when the repo is explicit and allowed.
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

    prompt = _build_research_prompt(task, codebase_context)

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

    result = _normalize_research_result(json.loads(text.strip()))

    if task.id is not None and task.lease_token:
        first_story = result.get("execution_stories", [])
        update_task_status(
            task.id,
            task.lease_token,
            "researching",
            event_message="Research plan refreshed.",
            research_json=result,
            execution_stories_json=result.get("execution_stories", []),
            current_story_id=first_story[0]["id"] if first_story else None,
        )

    return result
