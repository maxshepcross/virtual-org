"""Helpers for recording agent-run lifecycle events with lightweight heartbeats."""

from __future__ import annotations

import logging
import threading
from typing import Any

from config.constants import HEARTBEAT_INTERVAL_SECONDS
from models.control_plane import AgentRun, create_agent_run, update_agent_run

logger = logging.getLogger(__name__)


class AgentRunTracker:
    """Track one agent run from start to finish without leaking DB details into callers."""

    def __init__(
        self,
        *,
        task_id: int,
        story_id: str | None,
        agent_class: str,
        agent_role: str,
        resume_context_json: dict[str, Any] | None = None,
        heartbeat_interval_seconds: int | None = None,
    ) -> None:
        self.task_id = task_id
        self.story_id = story_id
        self.agent_class = agent_class
        self.agent_role = agent_role
        self.resume_context_json = resume_context_json or {}
        self.heartbeat_interval_seconds = max(
            5,
            heartbeat_interval_seconds or HEARTBEAT_INTERVAL_SECONDS,
        )
        self.run_id: int | None = None
        self.status = "running"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> int | None:
        run = create_agent_run(
            task_id=self.task_id,
            story_id=self.story_id,
            agent_class=self.agent_class,
            agent_role=self.agent_role,
            status=self.status,
            resume_context_json=self.resume_context_json,
        )
        self.run_id = run.id
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"agent-run-{self.run_id}",
            daemon=True,
        )
        self._thread.start()
        return self.run_id

    def complete(self, resume_context_json: dict[str, Any] | None = None) -> None:
        self._finish("completed", resume_context_json=resume_context_json)

    def fail(
        self,
        error_message: str,
        resume_context_json: dict[str, Any] | None = None,
    ) -> None:
        self._finish(
            "failed",
            resume_context_json=resume_context_json,
            error_message=error_message,
        )

    def _finish(
        self,
        status: str,
        *,
        resume_context_json: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        if self.run_id is None:
            return
        self.status = status
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        update_agent_run(
            self.run_id,
            status,
            resume_context_json=resume_context_json,
            error_message=error_message,
        )

    def _heartbeat_loop(self) -> None:
        if self.run_id is None:
            return
        while not self._stop_event.wait(self.heartbeat_interval_seconds):
            try:
                update_agent_run(
                    self.run_id,
                    self.status,
                    resume_context_json=self.resume_context_json,
                )
            except Exception:  # pragma: no cover - best effort heartbeat
                logger.exception("Failed to heartbeat agent run %s", self.run_id)


def start_agent_run(
    *,
    task_id: int | None,
    agent_role: str,
    story_id: str | None = None,
    agent_class: str = "control-plane",
    resume_context_json: dict[str, Any] | None = None,
) -> AgentRun:
    """Create one agent-run record for a worker phase."""
    return create_agent_run(
        task_id=task_id,
        story_id=story_id,
        agent_class=agent_class,
        agent_role=agent_role,
        resume_context_json=resume_context_json,
    )


def heartbeat_agent_run(
    run_id: int,
    *,
    resume_context_json: dict[str, Any] | None = None,
) -> AgentRun | None:
    """Mark an agent run as still active."""
    return update_agent_run(
        run_id,
        "running",
        resume_context_json=resume_context_json,
    )


def complete_agent_run(
    run_id: int,
    *,
    resume_context_json: dict[str, Any] | None = None,
) -> AgentRun | None:
    """Mark an agent run as completed."""
    return update_agent_run(
        run_id,
        "completed",
        resume_context_json=resume_context_json,
    )


def fail_agent_run(
    run_id: int,
    error_message: str,
    *,
    resume_context_json: dict[str, Any] | None = None,
) -> AgentRun | None:
    """Mark an agent run as failed."""
    return update_agent_run(
        run_id,
        "failed",
        resume_context_json=resume_context_json,
        error_message=error_message,
    )
