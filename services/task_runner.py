"""Task runner for the studio control plane.

This service is the small always-on worker that keeps queued tasks moving.
It claims one task at a time, keeps its lease alive while long steps run,
and advances the task through research and implementation.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from config.constants import HEARTBEAT_INTERVAL_SECONDS, TASK_STATUSES_FINAL
from implement import run_implementation
from models.task import (
    Task,
    claim_next_task,
    fail_stale_tasks,
    get_task,
    heartbeat_task,
    release_task,
    update_task_status,
)
from research import run_research
from services.agent_run_service import (
    complete_agent_run,
    fail_agent_run,
    heartbeat_agent_run,
    start_agent_run,
)

logger = logging.getLogger(__name__)


@dataclass
class TaskRunnerResult:
    """Small summary of one runner pass."""

    action: str
    message: str
    task_id: int | None = None
    task_status: str | None = None
    stale_failures: int = 0


class TaskRunner:
    """Single-process runner that advances one task at a time."""

    def __init__(
        self,
        *,
        worker_id: str = "studio-worker",
        poll_interval_seconds: int = 5,
        heartbeat_interval_seconds: int = HEARTBEAT_INTERVAL_SECONDS,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.worker_id = worker_id
        self.poll_interval_seconds = max(1, int(poll_interval_seconds))
        self.heartbeat_interval_seconds = max(1, int(heartbeat_interval_seconds))
        self._sleep = sleep_fn

    def run_once(self) -> TaskRunnerResult:
        """Run one worker pass: clean stale tasks, then claim and process one task."""
        stale_tasks = fail_stale_tasks()
        task = claim_next_task(self.worker_id)
        if not task:
            stale_count = len(stale_tasks)
            message = "No queued tasks available."
            if stale_count:
                message = f"Recovered {stale_count} stale task(s). No queued tasks available."
            return TaskRunnerResult(
                action="idle",
                message=message,
                stale_failures=stale_count,
            )

        result = self._process_task(task)
        result.stale_failures = len(stale_tasks)
        return result

    def run_forever(self, *, max_tasks: int | None = None) -> int:
        """Keep polling for work until interrupted or an optional task cap is reached."""
        processed = 0
        while max_tasks is None or processed < max_tasks:
            result = self.run_once()
            logger.info("%s", result.message)
            if result.action != "idle":
                processed += 1
                continue
            self._sleep(self.poll_interval_seconds)
        return processed

    def _process_task(self, task: Task) -> TaskRunnerResult:
        """Advance one claimed task through research and implementation."""
        current_task = task
        try:
            if not current_task.research_json:
                current_task = self._start_phase(
                    current_task,
                    status="researching",
                    event_message="Research started by the task runner.",
                )
                self._run_phase("researcher", current_task, lambda: run_research(current_task))
                current_task = self._refresh_task(current_task)
                if not current_task.research_json:
                    current_task = self._mark_failed(
                        current_task,
                        "Research finished without saving a plan.",
                    )
                    return TaskRunnerResult(
                        action="failed",
                        message=f"Task {current_task.id} failed: research did not save a plan.",
                        task_id=current_task.id,
                        task_status=current_task.status,
                    )
                recommendation = str(current_task.research_json.get("recommendation") or "proceed").strip().lower()
                if recommendation != "proceed":
                    current_task = self._mark_blocked(
                        current_task,
                        f"Research stopped this task with recommendation: {recommendation}.",
                    )
                    return TaskRunnerResult(
                        action="blocked",
                        message=f"Task {current_task.id} is blocked after research.",
                        task_id=current_task.id,
                        task_status=current_task.status,
                    )

            if current_task.status in TASK_STATUSES_FINAL:
                return TaskRunnerResult(
                    action="completed",
                    message=f"Task {current_task.id} is already {current_task.status}.",
                    task_id=current_task.id,
                    task_status=current_task.status,
                )

            current_task = self._start_phase(
                current_task,
                status="implementing",
                event_message="Implementation started by the task runner.",
                current_story_id=current_task.current_story_id,
                branch_name=current_task.branch_name,
            )
            implementation_result = self._run_phase(
                "implementer",
                current_task,
                lambda: run_implementation(current_task, current_task.research_json or {}),
            )
            current_task = self._refresh_task(current_task)

            if implementation_result.get("manual_verification_required"):
                return TaskRunnerResult(
                    action="awaiting_manual_verification",
                    message=f"Task {current_task.id} is waiting for manual verification.",
                    task_id=current_task.id,
                    task_status=current_task.status,
                )

            if current_task.status in TASK_STATUSES_FINAL:
                return TaskRunnerResult(
                    action="completed",
                    message=f"Task {current_task.id} finished with status {current_task.status}.",
                    task_id=current_task.id,
                    task_status=current_task.status,
                )

            return TaskRunnerResult(
                action="progressed",
                message=f"Task {current_task.id} advanced to {current_task.status}.",
                task_id=current_task.id,
                task_status=current_task.status,
            )
        except Exception as exc:  # pragma: no cover - exercised through tests
            logger.exception("Task %s failed inside task runner", task.id)
            current_task = self._mark_failed(task, f"Task runner error: {exc}")
            return TaskRunnerResult(
                action="failed",
                message=f"Task {current_task.id} failed: {exc}",
                task_id=current_task.id,
                task_status=current_task.status,
            )

    def _run_with_heartbeat(
        self,
        task: Task,
        operation: Callable[[], Any],
        *,
        agent_run_id: int | None = None,
    ) -> Any:
        """Run one long step while renewing the task lease in the background."""
        if task.id is None or not task.lease_token:
            return operation()

        result_box: dict[str, Any] = {}
        error_box: dict[str, BaseException] = {}
        done = threading.Event()

        def target() -> None:
            try:
                result_box["value"] = operation()
            except BaseException as exc:  # pragma: no cover - exercised through tests
                error_box["error"] = exc
            finally:
                done.set()

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        while not done.wait(self.heartbeat_interval_seconds):
            heartbeat_task(task.id, task.lease_token)
            if agent_run_id is not None:
                heartbeat_agent_run(agent_run_id)
        thread.join()

        if "error" in error_box:
            raise error_box["error"]
        return result_box.get("value")

    def _run_phase(self, agent_role: str, task: Task, operation: Callable[[], Any]) -> Any:
        """Track one research or implementation pass as an agent run."""
        agent_run_id: int | None = None
        try:
            agent_run = start_agent_run(
                task_id=task.id,
                story_id=task.current_story_id,
                agent_role=agent_role,
            )
            agent_run_id = agent_run.id
        except Exception:  # pragma: no cover - best effort tracking
            logger.exception("Could not start agent-run tracking for task %s", task.id)
        try:
            result = self._run_with_heartbeat(task, operation, agent_run_id=agent_run_id)
        except Exception as exc:
            if agent_run_id is not None:
                fail_agent_run(agent_run_id, error_message=str(exc)[:500])
            raise

        error_message = str(result.get("error") or "").strip() if isinstance(result, dict) else ""
        if error_message and not (isinstance(result, dict) and result.get("manual_verification_required")):
            if agent_run_id is not None:
                fail_agent_run(agent_run_id, error_message=error_message[:500])
        elif agent_run_id is not None:
            complete_agent_run(agent_run_id)
        return result

    def _refresh_task(self, task: Task) -> Task:
        """Reload the latest task state from the database after a phase completes."""
        if task.id is None:
            return task
        refreshed = get_task(task.id)
        return refreshed or task

    def _start_phase(self, task: Task, *, status: str, event_message: str, **fields: Any) -> Task:
        """Persist that a task phase has started before running work."""
        if task.id is None or not task.lease_token:
            return task
        return update_task_status(
            task.id,
            task.lease_token,
            status,
            event_message=event_message,
            **fields,
        )

    def _mark_failed(self, task: Task, error_message: str) -> Task:
        """Fail a task cleanly when the runner itself hits an unexpected error."""
        if task.id is None or not task.lease_token:
            task.status = "failed"
            task.error_message = error_message
            return task
        return update_task_status(
            task.id,
            task.lease_token,
            "failed",
            event_message=error_message,
            error_message=error_message[:500],
            current_story_id=task.current_story_id,
            branch_name=task.branch_name,
        )

    def _mark_blocked(self, task: Task, error_message: str) -> Task:
        """Block a task when research says not to proceed automatically."""
        if task.id is None or not task.lease_token:
            task.status = "blocked"
            task.error_message = error_message
            return task
        return release_task(
            task.id,
            task.lease_token,
            "blocked",
            event_message=error_message,
            error_message=error_message[:500],
            current_story_id=task.current_story_id,
            branch_name=task.branch_name,
        )
