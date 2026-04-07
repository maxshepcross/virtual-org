"""GitHub operations — branch creation, reuse, and PR opening."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def slugify(text: str, max_len: int = 40) -> str:
    """Turn a title into a branch-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


def _run_git(repo_dir: Path, args: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Run a git command and raise if it fails."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git command failed")
    return result


def create_branch(repo_dir: Path, task_id: int, title: str) -> str:
    """Create a fresh task branch from origin/main without rewriting dirty repos."""
    branch = f"studio/task-{task_id}-{slugify(title)}"

    _run_git(repo_dir, ["fetch", "origin", "main"], timeout=60)
    status = _run_git(repo_dir, ["status", "--porcelain"], timeout=10).stdout.strip()
    if status:
        raise RuntimeError(f"Refusing to create branch in dirty repo: {repo_dir}")

    _run_git(repo_dir, ["checkout", "-B", branch, "origin/main"], timeout=30)

    return branch


def ensure_branch(repo_dir: Path, task_id: int, title: str, existing_branch: str | None = None) -> str:
    """Reuse an existing clean branch or create a fresh one from origin/main."""
    _run_git(repo_dir, ["fetch", "origin", "main"], timeout=60)
    status = _run_git(repo_dir, ["status", "--porcelain"], timeout=10).stdout.strip()
    if status:
        raise RuntimeError(f"Refusing to switch branch in dirty repo: {repo_dir}")

    if existing_branch:
        try:
            _run_git(repo_dir, ["checkout", existing_branch], timeout=30)
            return existing_branch
        except RuntimeError:
            _run_git(repo_dir, ["checkout", "-B", existing_branch, f"origin/{existing_branch}"], timeout=30)
            return existing_branch

    return create_branch(repo_dir, task_id, title)


def commit_and_push(repo_dir: Path, branch: str, message: str) -> bool:
    """Stage all changes, commit, and push."""
    subprocess.run(
        ["git", "add", "-A"],
        cwd=repo_dir, capture_output=True, timeout=10,
    )

    # Check if there are changes to commit
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_dir, capture_output=True, text=True, timeout=10,
    )
    if not status.stdout.strip():
        logger.info("No changes to commit on branch %s", branch)
        return {"status": "no_changes"}

    commit_result = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo_dir, capture_output=True, text=True, timeout=30,
    )
    if commit_result.returncode != 0:
        logger.error("Commit failed: %s", commit_result.stderr)
        return {
            "status": "commit_failed",
            "error": commit_result.stderr.strip() or commit_result.stdout.strip() or "git commit failed",
        }

    env = os.environ.copy()
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        # Set up auth for push
        subprocess.run(
            ["git", "remote", "set-url", "origin",
             f"https://x-access-token:{github_token}@github.com/{_get_repo_name(repo_dir)}.git"],
            cwd=repo_dir, capture_output=True, timeout=10,
        )

    result = subprocess.run(
        ["git", "push", "-u", "origin", branch],
        cwd=repo_dir, capture_output=True, text=True, timeout=60,
    )

    if result.returncode != 0:
        logger.error("Push failed: %s", result.stderr)
        return {
            "status": "push_failed",
            "error": result.stderr.strip() or result.stdout.strip() or "git push failed",
        }

    return {"status": "pushed"}


def open_pr(
    repo_dir: Path,
    repo: str,
    branch: str,
    title: str,
    body: str,
) -> dict | None:
    """Open a PR using the gh CLI. Returns {pr_url, pr_number} or None."""
    env = os.environ.copy()
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        env["GH_TOKEN"] = github_token

    result = subprocess.run(
        [
            "gh", "pr", "create",
            "--repo", repo,
            "--head", branch,
            "--title", title,
            "--body", body,
        ],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )

    if result.returncode != 0:
        logger.error("PR creation failed: %s", result.stderr)
        return None

    pr_url = result.stdout.strip()
    # Extract PR number from URL
    pr_number = None
    match = re.search(r"/pull/(\d+)", pr_url)
    if match:
        pr_number = int(match.group(1))

    return {"pr_url": pr_url, "pr_number": pr_number}


def _get_repo_name(repo_dir: Path) -> str:
    """Extract owner/repo from git remote."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_dir, capture_output=True, text=True, timeout=10,
    )
    url = result.stdout.strip()
    # Handle https://github.com/owner/repo.git or git@github.com:owner/repo.git
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    return match.group(1) if match else ""
