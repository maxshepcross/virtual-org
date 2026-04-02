"""Implementation agent — uses Claude Code as a subprocess to make changes and open PRs."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from config.constants import ALLOWED_REPOS, IMPLEMENT_MODEL, IMPLEMENT_TIMEOUT_SECONDS
from config.env import load_project_env
from models.task import Task
from services.github_ops import create_branch, commit_and_push, open_pr

load_project_env()
logger = logging.getLogger(__name__)

REPOS_DIR = Path(__file__).parent / ".repos"


def _format_timeout(seconds: int) -> str:
    """Return a human-readable timeout string for Slack and task logs."""
    if seconds % 60 == 0:
        minutes = seconds // 60
        unit = "minute" if minutes == 1 else "minutes"
        return f"{minutes} {unit}"
    unit = "second" if seconds == 1 else "seconds"
    return f"{seconds} {unit}"


def _build_claude_prompt(task: Task, research: dict) -> str:
    """Build the prompt that Claude Code will execute."""
    files_to_modify = research.get("files_to_modify", [])
    files_to_create = research.get("files_to_create", [])
    approach = research.get("approach", [])
    risks = research.get("risks", [])

    prompt = f"""You are implementing a feature for the Tempa codebase.

## Task
{task.title}

## Description
{task.description}

## Implementation Plan (from research)
{chr(10).join(f"- {step}" for step in approach)}

## Files to modify
{chr(10).join(f"- {f}" for f in files_to_modify) or "None identified"}

## Files to create
{chr(10).join(f"- {f}" for f in files_to_create) or "None"}

## Risks to watch for
{chr(10).join(f"- {r}" for r in risks) or "None identified"}

## Instructions
1. Make the changes described in the implementation plan
2. Keep changes minimal and focused — only change what's needed
3. Follow existing code patterns and style
4. Run tests if they exist: python -m pytest tests/ -x
5. Do NOT update documentation files (CLAUDE.md, CHANGELOG.md, etc) — that's done separately
6. Do NOT add unnecessary error handling, comments, or type annotations to code you didn't change
"""
    return prompt


def run_implementation(task: Task, research: dict) -> dict:
    """Run Claude Code to implement the changes and open a PR.

    Returns dict with pr_url, pr_number, branch_name.
    """
    if not task.target_repo or task.target_repo not in ALLOWED_REPOS:
        return {"error": f"Repo {task.target_repo} not in allowed list"}

    repo_dir = REPOS_DIR / task.target_repo.replace("/", "_")
    if not repo_dir.exists():
        return {"error": f"Repo not cloned at {repo_dir}"}

    # Create branch
    branch = create_branch(repo_dir, task.id, task.title)
    logger.info("Created branch: %s", branch)

    # Build prompt for Claude Code
    prompt = _build_claude_prompt(task, research)

    # Run Claude Code as a subprocess
    try:
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--dangerously-skip-permissions",
                "-p", prompt,
            ],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=IMPLEMENT_TIMEOUT_SECONDS,
            env={**os.environ, "CLAUDE_MODEL": IMPLEMENT_MODEL},
        )

        if result.returncode != 0:
            logger.error("Claude Code failed: %s", result.stderr[:500])
            return {
                "branch_name": branch,
                "error": f"Claude Code exit code {result.returncode}: {result.stderr[:200]}",
            }

        claude_output = result.stdout[-2000:]  # Last 2000 chars of output
    except subprocess.TimeoutExpired:
        return {
            "branch_name": branch,
            "error": f"Claude Code timed out after {_format_timeout(IMPLEMENT_TIMEOUT_SECONDS)}",
        }

    # Commit and push
    commit_msg = f"virtual-org: {task.title}\n\nIdea #{task.idea_id} → Task #{task.id}\nImplemented by Virtual Org agent."
    pushed = commit_and_push(repo_dir, branch, commit_msg)

    if not pushed:
        return {
            "branch_name": branch,
            "error": "No changes to commit (Claude Code made no modifications)",
            "claude_output": claude_output,
        }

    # Open PR
    pr_body = f"""## Summary

{task.description}

## Research findings

{research.get('summary', 'N/A')}

## Approach

{chr(10).join(f"- {step}" for step in research.get('approach', []))}

## Risks

{chr(10).join(f"- {r}" for r in research.get('risks', [])) or "None identified"}

---

*Automated by [Virtual Org](https://github.com/maxshepcross/virtual-org) — Idea #{task.idea_id} → Task #{task.id}*
"""

    pr_result = open_pr(
        repo_dir=repo_dir,
        repo=task.target_repo,
        branch=branch,
        title=task.title,
        body=pr_body,
    )

    if not pr_result:
        return {
            "branch_name": branch,
            "error": "Push succeeded but PR creation failed",
            "claude_output": claude_output,
        }

    return {
        "branch_name": branch,
        "pr_url": pr_result["pr_url"],
        "pr_number": pr_result["pr_number"],
        "claude_output": claude_output,
    }
