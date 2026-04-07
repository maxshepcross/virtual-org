"""Implementation helper that applies studio tasks in explicit target repos."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.constants import ALLOWED_REPOS, IMPLEMENT_MODEL, IMPLEMENT_TIMEOUT_SECONDS
from config.env import load_project_env
from models.task import Task, update_task_status
from services.github_ops import ensure_branch, commit_and_push, open_pr

load_project_env()
logger = logging.getLogger(__name__)

REPOS_DIR = Path(__file__).parent / ".repos"


def _format_timeout(seconds: int) -> str:
    """Return a human-readable timeout string."""
    if seconds % 60 == 0:
        minutes = seconds // 60
        unit = "minute" if minutes == 1 else "minutes"
        return f"{minutes} {unit}"
    unit = "second" if seconds == 1 else "seconds"
    return f"{seconds} {unit}"


def _coerce_story_list(value: Any) -> list[dict[str, Any]]:
    """Normalize stored stories into a mutable list of dicts."""
    if not isinstance(value, list):
        return []
    stories: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            stories.append(deepcopy(item))
    return stories


def _fallback_story_from_research(research: dict[str, Any]) -> list[dict[str, Any]]:
    """Create one coarse execution story when research did not return slices."""
    summary = research.get("summary", "")
    approach = research.get("approach", [])
    suggested_files = [
        *research.get("files_to_modify", []),
        *research.get("files_to_create", []),
    ]
    return [{
        "id": "STORY-1",
        "title": "Implement approved plan",
        "summary": summary,
        "priority": 1,
        "acceptance_criteria": approach or ["Implement the approved change safely."],
        "verification": ["Run available automated checks"],
        "suggested_files": suggested_files,
        "status": "pending",
    }]


def _get_execution_stories(task: Task, research: dict[str, Any]) -> list[dict[str, Any]]:
    """Choose the best available execution plan for this run."""
    stories = _coerce_story_list(task.execution_stories_json)
    if stories:
        return stories

    stories = _coerce_story_list(research.get("execution_stories"))
    if stories:
        return stories

    return _fallback_story_from_research(research)


def _select_next_story(stories: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the next story to work on."""
    for status in ("in_progress", "pending"):
        for story in sorted(stories, key=lambda item: (item.get("priority", 999), item.get("id", ""))):
            if story.get("status") == status:
                return story
    return None


def _build_progress_note(story: dict[str, Any], status: str, message: str) -> dict[str, Any]:
    """Create one append-only progress note entry."""
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "story_id": story.get("id"),
        "story_title": story.get("title"),
        "status": status,
        "message": message,
    }


def _has_python_tests(repo_dir: Path) -> bool:
    """Detect a basic Python test layout before auto-running pytest."""
    return (
        (repo_dir / "tests").exists()
        or (repo_dir / "pytest.ini").exists()
        or (repo_dir / "pyproject.toml").exists()
    )


def _run_story_verification(repo_dir: Path, story: dict[str, Any]) -> list[dict[str, Any]]:
    """Run the verification steps we can automate and record the rest for manual follow-up."""
    results: list[dict[str, Any]] = []
    for step in story.get("verification", []):
        lowered = str(step).lower()
        if "browser" in lowered or "manual" in lowered:
            results.append({
                "step": step,
                "status": "manual_required",
                "details": "This step still needs a human or browser-based check.",
            })
            continue

        if "test" in lowered or "pytest" in lowered:
            if not _has_python_tests(repo_dir):
                results.append({
                    "step": step,
                    "status": "manual_required",
                    "details": "No Python test suite was detected for automatic verification.",
                })
                continue

            proc = subprocess.run(
                ["python", "-m", "pytest", "tests/", "-x"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=IMPLEMENT_TIMEOUT_SECONDS,
            )
            results.append({
                "step": step,
                "status": "passed" if proc.returncode == 0 else "failed",
                "details": (proc.stdout or proc.stderr)[-1000:],
            })
            continue

        if "typecheck" in lowered:
            results.append({
                "step": step,
                "status": "manual_required",
                "details": "Automatic typecheck commands are not configured in this control-plane version.",
            })
            continue

        results.append({
            "step": step,
            "status": "manual_required",
            "details": "No automatic verifier is configured for this step yet.",
        })

    if not results:
        results.append({
            "step": "No verification requested",
            "status": "not_requested",
            "details": "",
        })
    return results


def _verification_failed(results: list[dict[str, Any]]) -> bool:
    """Return True when any automatic verification step failed."""
    return any(result.get("status") == "failed" for result in results)


def _verification_requires_manual_review(results: list[dict[str, Any]]) -> bool:
    """Return True when progress should stop for manual verification."""
    return any(result.get("status") == "manual_required" for result in results)


def _find_manual_review_story(stories: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find a story that is waiting on manual verification."""
    for story in sorted(stories, key=lambda item: (item.get("priority", 999), item.get("id", ""))):
        if story.get("status") == "awaiting_manual_verification":
            return story
    return None


def _all_stories_completed(stories: list[dict[str, Any]]) -> bool:
    """Return True when every execution story is complete."""
    return bool(stories) and all(story.get("status") == "completed" for story in stories)


def _persist_task_progress(task: Task, status: str, event_message: str, **fields: Any) -> None:
    """Persist implementation progress when this run is attached to a queued task."""
    if task.id is None or not task.lease_token:
        return
    update_task_status(task.id, task.lease_token, status, event_message=event_message, **fields)


def _open_pr_for_completed_stories(
    task: Task,
    research: dict[str, Any],
    repo_dir: Path,
    branch: str,
    execution_stories: list[dict[str, Any]],
    progress_notes: list[dict[str, Any]],
    verification_log: list[dict[str, Any]],
) -> dict[str, Any]:
    """Open the PR after all stories have been completed and verified."""
    pr_body = f"""## Summary

{task.description}

## Research findings

{research.get('summary', 'N/A')}

## Approach

{chr(10).join(f"- {step}" for step in research.get('approach', []))}

## Stories completed

{chr(10).join(f"- {story.get('id')}: {story.get('title')}" for story in execution_stories)}

## Risks

{chr(10).join(f"- {r}" for r in research.get('risks', [])) or "None identified"}

---

*Automated by the AI Venture Studio workflow — Task #{task.id}*
"""

    pr_result = open_pr(
        repo_dir=repo_dir,
        repo=task.target_repo,
        branch=branch,
        title=task.title,
        body=pr_body,
    )

    if not pr_result:
        _persist_task_progress(
            task,
            "failed",
            "Push succeeded but PR creation failed after the final story.",
            execution_stories_json=execution_stories,
            progress_notes_json=progress_notes,
            verification_json=verification_log,
            current_story_id=None,
            branch_name=branch,
            error_message="Push succeeded but PR creation failed",
        )
        return {
            "branch_name": branch,
            "error": "Push succeeded but PR creation failed",
        }

    _persist_task_progress(
        task,
        "pr_open",
        "All execution stories completed and PR opened.",
        execution_stories_json=execution_stories,
        progress_notes_json=progress_notes,
        verification_json=verification_log,
        current_story_id=None,
        branch_name=branch,
        pr_url=pr_result["pr_url"],
        pr_number=pr_result["pr_number"],
        pr_status="open",
    )
    return {
        "branch_name": branch,
        "pr_url": pr_result["pr_url"],
        "pr_number": pr_result["pr_number"],
        "execution_stories_json": execution_stories,
        "progress_notes_json": progress_notes,
        "verification_json": verification_log,
        "current_story_id": None,
        "completed_all_stories": True,
        "next_story_id": None,
    }


def _build_claude_prompt(
    task: Task,
    research: dict,
    selected_story: dict[str, Any] | None = None,
    execution_stories: list[dict[str, Any]] | None = None,
) -> str:
    """Build the prompt that Claude Code will execute."""
    files_to_modify = research.get("files_to_modify", [])
    files_to_create = research.get("files_to_create", [])
    approach = research.get("approach", [])
    risks = research.get("risks", [])
    execution_stories = execution_stories or research.get("execution_stories", [])

    story_lines = []
    for story in execution_stories:
        title = story.get("title", "Unnamed story")
        priority = story.get("priority", "?")
        story_lines.append(f"- P{priority}: {title}")
        summary = story.get("summary")
        if summary:
            story_lines.append(f"  Summary: {summary}")
        acceptance = story.get("acceptance_criteria", [])
        if acceptance:
            story_lines.extend(f"  Acceptance: {item}" for item in acceptance)
        verification = story.get("verification", [])
        if verification:
            story_lines.extend(f"  Verify: {item}" for item in verification)
        suggested_files = story.get("suggested_files", [])
        if suggested_files:
            story_lines.extend(f"  File: {item}" for item in suggested_files)

    prompt = f"""You are implementing a change for AI Venture Studio.

## Task
{task.title}

## Description
{task.description}

## Target repo
{task.target_repo or "Not provided"}

## Implementation Plan (from research)
{chr(10).join(f"- {step}" for step in approach)}

## Execution Stories
{chr(10).join(story_lines) or "No execution stories provided"}

## Selected Story For This Run
{selected_story.get("id") if selected_story else "None"}
{selected_story.get("title") if selected_story else "No selected story"}
{selected_story.get("summary") if selected_story else ""}
{chr(10).join(f"- Acceptance: {item}" for item in selected_story.get("acceptance_criteria", [])) if selected_story else ""}
{chr(10).join(f"- Verify: {item}" for item in selected_story.get("verification", [])) if selected_story else ""}
{chr(10).join(f"- File: {item}" for item in selected_story.get("suggested_files", [])) if selected_story else ""}

## Files to modify
{chr(10).join(f"- {f}" for f in files_to_modify) or "None identified"}

## Files to create
{chr(10).join(f"- {f}" for f in files_to_create) or "None"}

## Risks to watch for
{chr(10).join(f"- {r}" for r in risks) or "None identified"}

## Instructions
1. Work only on the selected story for this run unless a tiny supporting change is required to complete it safely
2. Make the changes described in the implementation plan
3. Use the execution stories as the preferred order of work if they are provided
4. Only edit the explicit target repo. Do not change the studio control repo.
5. Keep changes minimal and focused
6. If the task details and target repo do not match, stop and explain the mismatch
7. Run tests if they exist: python -m pytest tests/ -x
8. Do NOT update documentation files unless the plan explicitly calls for it
9. Do NOT add unnecessary comments or refactors outside the task
"""
    return prompt


def run_implementation(task: Task, research: dict) -> dict:
    """Run Claude Code to implement the changes and open a PR.

    Returns dict with pr_url, pr_number, branch_name.
    """
    if not task.target_repo or task.target_repo not in ALLOWED_REPOS:
        _persist_task_progress(
            task,
            "failed",
            f"Blocked implementation for disallowed repo: {task.target_repo}",
            error_message=f"Repo {task.target_repo} not in allowed list",
        )
        return {"error": f"Repo {task.target_repo} not in allowed list"}

    repo_dir = REPOS_DIR / task.target_repo.replace("/", "_")
    if not repo_dir.exists():
        _persist_task_progress(
            task,
            "failed",
            f"Blocked implementation because repo clone is missing: {repo_dir}",
            error_message=f"Repo not cloned at {repo_dir}",
        )
        return {"error": f"Repo not cloned at {repo_dir}"}

    execution_stories = _get_execution_stories(task, research)
    manual_review_story = _find_manual_review_story(execution_stories)
    if manual_review_story:
        _persist_task_progress(
            task,
            "implementing",
            f"Waiting for manual verification on {manual_review_story.get('id')}.",
            execution_stories_json=execution_stories,
            progress_notes_json=task.progress_notes_json or [],
            verification_json=task.verification_json or [],
            current_story_id=manual_review_story.get("id"),
            branch_name=task.branch_name,
        )
        return {
            "branch_name": task.branch_name,
            "execution_stories_json": execution_stories,
            "progress_notes_json": task.progress_notes_json or [],
            "verification_json": task.verification_json or [],
            "current_story_id": manual_review_story.get("id"),
            "manual_verification_required": True,
            "error": "Manual verification required for the selected story",
        }

    selected_story = _select_next_story(execution_stories)
    if not selected_story:
        if _all_stories_completed(execution_stories):
            branch = task.branch_name
            if not branch:
                _persist_task_progress(
                    task,
                    "failed",
                    "All stories are complete but there is no branch to open a PR from.",
                    execution_stories_json=execution_stories,
                    progress_notes_json=task.progress_notes_json or [],
                    verification_json=task.verification_json or [],
                    current_story_id=None,
                    error_message="All stories completed but branch_name is missing",
                )
                return {"error": "All stories completed but branch_name is missing"}

            return _open_pr_for_completed_stories(
                task=task,
                research=research,
                repo_dir=repo_dir,
                branch=branch,
                execution_stories=execution_stories,
                progress_notes=deepcopy(task.progress_notes_json or []),
                verification_log=deepcopy(task.verification_json or []),
            )

        _persist_task_progress(
            task,
            "done",
            "No pending execution stories remain.",
            execution_stories_json=execution_stories,
            progress_notes_json=task.progress_notes_json or [],
            verification_json=task.verification_json or [],
            current_story_id=None,
            branch_name=task.branch_name,
        )
        return {
            "branch_name": task.branch_name,
            "execution_stories_json": execution_stories,
            "progress_notes_json": task.progress_notes_json or [],
            "verification_json": task.verification_json or [],
            "current_story_id": None,
            "error": "No pending execution stories remain",
        }

    progress_notes = deepcopy(task.progress_notes_json or [])
    verification_log = deepcopy(task.verification_json or [])

    # Reuse existing branch for later stories, or create a fresh one for the first story.
    branch = ensure_branch(repo_dir, task.id or 0, task.title, task.branch_name)
    logger.info("Using branch: %s", branch)
    selected_story["status"] = "in_progress"
    _persist_task_progress(
        task,
        "implementing",
        f"Started {selected_story.get('id')}: {selected_story.get('title')}",
        execution_stories_json=execution_stories,
        progress_notes_json=progress_notes,
        verification_json=verification_log,
        current_story_id=selected_story.get("id"),
        branch_name=branch,
    )

    # Build prompt for Claude Code
    prompt = _build_claude_prompt(task, research, selected_story, execution_stories)

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
            selected_story["status"] = "failed"
            progress_notes.append(
                _build_progress_note(
                    selected_story,
                    "failed",
                    f"Claude Code exited with status {result.returncode}.",
                )
            )
            logger.error("Claude Code failed: %s", result.stderr[:500])
            _persist_task_progress(
                task,
                "failed",
                f"Claude Code failed during {selected_story.get('id')}.",
                execution_stories_json=execution_stories,
                progress_notes_json=progress_notes,
                verification_json=verification_log,
                current_story_id=selected_story.get("id"),
                branch_name=branch,
                error_message=f"Claude Code exit code {result.returncode}: {result.stderr[:200]}",
            )
            return {
                "branch_name": branch,
                "execution_stories_json": execution_stories,
                "progress_notes_json": progress_notes,
                "verification_json": verification_log,
                "current_story_id": selected_story.get("id"),
                "error": f"Claude Code exit code {result.returncode}: {result.stderr[:200]}",
            }

        claude_output = result.stdout[-2000:]  # Last 2000 chars of output
    except subprocess.TimeoutExpired:
        selected_story["status"] = "failed"
        progress_notes.append(
            _build_progress_note(
                selected_story,
                "failed",
                "Claude Code timed out before the selected story completed.",
            )
        )
        _persist_task_progress(
            task,
            "failed",
            f"Claude Code timed out during {selected_story.get('id')}.",
            execution_stories_json=execution_stories,
            progress_notes_json=progress_notes,
            verification_json=verification_log,
            current_story_id=selected_story.get("id"),
            branch_name=branch,
            error_message=f"Claude Code timed out after {_format_timeout(IMPLEMENT_TIMEOUT_SECONDS)}",
        )
        return {
            "branch_name": branch,
            "execution_stories_json": execution_stories,
            "progress_notes_json": progress_notes,
            "verification_json": verification_log,
            "current_story_id": selected_story.get("id"),
            "error": f"Claude Code timed out after {_format_timeout(IMPLEMENT_TIMEOUT_SECONDS)}",
        }

    verification_results = _run_story_verification(repo_dir, selected_story)
    verification_log.append({
        "story_id": selected_story.get("id"),
        "story_title": selected_story.get("title"),
        "at": datetime.now(timezone.utc).isoformat(),
        "results": verification_results,
    })
    if _verification_failed(verification_results):
        selected_story["status"] = "failed"
        progress_notes.append(
            _build_progress_note(
                selected_story,
                "failed",
                "Automated verification failed for this story.",
            )
        )
        _persist_task_progress(
            task,
            "failed",
            f"Verification failed for {selected_story.get('id')}.",
            execution_stories_json=execution_stories,
            progress_notes_json=progress_notes,
            verification_json=verification_log,
            current_story_id=selected_story.get("id"),
            branch_name=branch,
            error_message="Automated verification failed for the selected story",
        )
        return {
            "branch_name": branch,
            "claude_output": claude_output,
            "execution_stories_json": execution_stories,
            "progress_notes_json": progress_notes,
            "verification_json": verification_log,
            "current_story_id": selected_story.get("id"),
            "error": "Automated verification failed for the selected story",
        }

    # Commit and push
    commit_msg = (
        f"studio: {task.title} [{selected_story.get('id')}]\n\n"
        f"Task #{task.id}\n"
        f"Story: {selected_story.get('title')}\n"
        "Implemented by the AI Venture Studio workflow."
    )
    push_result = commit_and_push(repo_dir, branch, commit_msg)

    if push_result["status"] != "pushed":
        selected_story["status"] = "failed"
        error_message = {
            "no_changes": "No changes to commit (Claude Code made no modifications)",
            "commit_failed": push_result.get("error") or "git commit failed",
            "push_failed": push_result.get("error") or "git push failed",
        }[push_result["status"]]
        progress_notes.append(
            _build_progress_note(
                selected_story,
                "failed",
                error_message,
            )
        )
        _persist_task_progress(
            task,
            "failed",
            f"{selected_story.get('id')} failed: {error_message}",
            execution_stories_json=execution_stories,
            progress_notes_json=progress_notes,
            verification_json=verification_log,
            current_story_id=selected_story.get("id"),
            branch_name=branch,
            error_message=error_message,
        )
        return {
            "branch_name": branch,
            "execution_stories_json": execution_stories,
            "progress_notes_json": progress_notes,
            "verification_json": verification_log,
            "current_story_id": selected_story.get("id"),
            "error": error_message,
            "claude_output": claude_output,
        }

    if _verification_requires_manual_review(verification_results):
        selected_story["status"] = "awaiting_manual_verification"
        progress_notes.append(
            _build_progress_note(
                selected_story,
                "awaiting_manual_verification",
                "Automated work is complete, but manual verification is still required.",
            )
        )
        _persist_task_progress(
            task,
            "implementing",
            f"Waiting for manual verification on {selected_story.get('id')}.",
            execution_stories_json=execution_stories,
            progress_notes_json=progress_notes,
            verification_json=verification_log,
            current_story_id=selected_story.get("id"),
            branch_name=branch,
        )
        return {
            "branch_name": branch,
            "claude_output": claude_output,
            "execution_stories_json": execution_stories,
            "progress_notes_json": progress_notes,
            "verification_json": verification_log,
            "current_story_id": selected_story.get("id"),
            "manual_verification_required": True,
            "error": "Manual verification required for the selected story",
        }

    selected_story["status"] = "completed"
    progress_notes.append(
        _build_progress_note(
            selected_story,
            "completed",
            "Story implemented and changes pushed.",
        )
    )

    next_story = _select_next_story(execution_stories)
    if next_story:
        _persist_task_progress(
            task,
            "implementing",
            f"Completed {selected_story.get('id')}; queued {next_story.get('id')} next.",
            execution_stories_json=execution_stories,
            progress_notes_json=progress_notes,
            verification_json=verification_log,
            current_story_id=next_story.get("id"),
            branch_name=branch,
        )
        return {
            "branch_name": branch,
            "claude_output": claude_output,
            "execution_stories_json": execution_stories,
            "progress_notes_json": progress_notes,
            "verification_json": verification_log,
            "current_story_id": next_story.get("id"),
            "completed_all_stories": False,
            "next_story_id": next_story.get("id"),
        }

    result = _open_pr_for_completed_stories(
        task=task,
        research=research,
        repo_dir=repo_dir,
        branch=branch,
        execution_stories=execution_stories,
        progress_notes=progress_notes,
        verification_log=verification_log,
    )
    result["claude_output"] = claude_output
    return result
