"""Internal HTTP API for the control-plane services that OpenClaw will call."""

from __future__ import annotations

import os
from threading import Lock, Thread
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from models.control_plane import (
    append_agent_run_artifact,
    create_agent_run,
    get_task_control_state,
    list_attention_items,
    update_agent_run,
)
from services.approval_service import (
    ApprovalCreateRequest,
    ApprovalResolutionRequest,
    create_approval,
    get_pending_approvals,
    resolve_approval,
)
from services.briefing_service import generate_briefing
from services.policy_engine import PolicyEvaluationRequest
from services.policy_service import evaluate_and_record_policy
from services.slack_agent import (
    SlackSignatureError,
    handle_interactivity,
    handle_slack_event,
    parse_interactivity_payload,
    verify_slack_signature,
)
from services.signal_service import SignalInput, record_signal
from services.task_runner import TaskRunner

app = FastAPI(title="AI Venture Studio Control API", version="0.1.0")
_worker_run_lock = Lock()


def _run_worker_pass(worker_id: str, poll_interval_seconds: int) -> None:
    """Advance one worker pass in the background so the chief stays responsive."""
    try:
        runner = TaskRunner(
            worker_id=worker_id,
            poll_interval_seconds=poll_interval_seconds,
        )
        app.state.last_worker_result = runner.run_once().__dict__
    except Exception as exc:  # pragma: no cover - defensive background logging
        app.state.last_worker_result = {
            "action": "failed",
            "message": f"Background worker pass failed: {exc}",
        }
    finally:
        _worker_run_lock.release()


class AgentRunCreateRequest(BaseModel):
    task_id: int | None = None
    story_id: str | None = None
    run_key: str | None = None
    parent_run_id: int | None = None
    run_kind: str = "interactive"
    trigger_source: str = "manual"
    triggered_by: str | None = None
    agent_class: str
    agent_role: str
    repo_name: str | None = None
    branch_name: str | None = None
    slack_channel_id: str | None = None
    slack_thread_ts: str | None = None
    openclaw_session_id: str | None = None
    status: str = "running"
    artifact_summary_json: list[dict] | None = None
    context_json: dict | None = None
    tool_bundle_json: list[str] | None = None
    resume_context_json: dict | None = None


class AgentRunUpdateRequest(BaseModel):
    status: str | None = None
    approved_by: str | None = None
    completed_by: str | None = None
    branch_name: str | None = None
    pr_url: str | None = None
    slack_channel_id: str | None = None
    slack_thread_ts: str | None = None
    context_json: dict | None = None
    tool_bundle_json: list[str] | None = None
    resume_context_json: dict | None = None
    error_message: str | None = None
    openclaw_session_id: str | None = None


class AgentRunArtifactRequest(BaseModel):
    artifact: dict


def require_control_api_token(authorization: str | None = Header(default=None)) -> None:
    expected_token = os.getenv("CONTROL_API_TOKEN", "").strip()
    if not expected_token:
        raise HTTPException(status_code=503, detail="CONTROL_API_TOKEN is not configured.")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")

    provided_token = authorization.removeprefix("Bearer ").strip()
    if provided_token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid bearer token.")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/slack/events")
async def slack_events_endpoint(request: Request) -> JSONResponse:
    raw_body = await request.body()
    try:
        verify_slack_signature(
            timestamp=request.headers.get("X-Slack-Request-Timestamp"),
            signature=request.headers.get("X-Slack-Signature"),
            body=raw_body,
        )
    except SlackSignatureError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    payload = await request.json()
    if payload.get("type") == "url_verification":
        return PlainTextResponse(str(payload.get("challenge") or ""))
    return JSONResponse(handle_slack_event(payload))


@app.post("/slack/interactivity")
async def slack_interactivity_endpoint(request: Request) -> JSONResponse:
    raw_body = await request.body()
    try:
        verify_slack_signature(
            timestamp=request.headers.get("X-Slack-Request-Timestamp"),
            signature=request.headers.get("X-Slack-Signature"),
            body=raw_body,
        )
    except SlackSignatureError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    form_payload = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
    payload = parse_interactivity_payload((form_payload.get("payload") or [""])[0])
    return JSONResponse(handle_interactivity(payload))


@app.post("/v1/signals", status_code=201)
def create_signal_endpoint(payload: SignalInput, _: None = Depends(require_control_api_token)) -> dict:
    result = record_signal(payload)
    return {
        "signal": result["signal"].model_dump() if result["signal"] else None,
        "attention_item": result["attention_item"].model_dump() if result["attention_item"] else None,
        "deduped": result["deduped"],
    }


@app.get("/v1/attention")
def list_attention_endpoint(limit: int = 50, _: None = Depends(require_control_api_token)) -> dict[str, list[dict]]:
    items = list_attention_items(limit=limit)
    return {"items": [item.model_dump() for item in items]}


@app.post("/v1/policy/evaluate")
def evaluate_policy_endpoint(payload: PolicyEvaluationRequest, _: None = Depends(require_control_api_token)) -> dict:
    result = evaluate_and_record_policy(payload)
    return result.model_dump()


@app.post("/v1/approvals", status_code=201)
def create_approval_endpoint(payload: ApprovalCreateRequest, _: None = Depends(require_control_api_token)) -> dict:
    try:
        approval = create_approval(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return approval.model_dump()


@app.get("/v1/approvals/pending")
def list_pending_approvals_endpoint(limit: int = 50, _: None = Depends(require_control_api_token)) -> dict[str, list[dict]]:
    approvals = get_pending_approvals(limit=limit)
    return {"items": [approval.model_dump() for approval in approvals]}


@app.post("/v1/approvals/{approval_id}/resolve")
def resolve_approval_endpoint(
    approval_id: int,
    payload: ApprovalResolutionRequest,
    _: None = Depends(require_control_api_token),
) -> dict:
    try:
        approval = resolve_approval(approval_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return approval.model_dump()


@app.get("/v1/tasks/{task_id}/state")
def task_state_endpoint(task_id: int, _: None = Depends(require_control_api_token)) -> dict:
    state = get_task_control_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Task {task_id} was not found.")
    return {
        "task": state["task"].model_dump(),
        "attention_items": [item.model_dump() for item in state["attention_items"]],
        "approval_requests": [item.model_dump() for item in state["approval_requests"]],
        "policy_decisions": [item.model_dump() for item in state["policy_decisions"]],
        "agent_runs": [item.model_dump() for item in state["agent_runs"]],
    }


@app.post("/v1/agent-runs", status_code=201)
def create_agent_run_endpoint(payload: AgentRunCreateRequest, _: None = Depends(require_control_api_token)) -> dict:
    run = create_agent_run(
        task_id=payload.task_id,
        story_id=payload.story_id,
        run_key=payload.run_key,
        parent_run_id=payload.parent_run_id,
        run_kind=payload.run_kind,
        trigger_source=payload.trigger_source,
        triggered_by=payload.triggered_by,
        agent_class=payload.agent_class,
        agent_role=payload.agent_role,
        repo_name=payload.repo_name,
        branch_name=payload.branch_name,
        slack_channel_id=payload.slack_channel_id,
        slack_thread_ts=payload.slack_thread_ts,
        openclaw_session_id=payload.openclaw_session_id,
        status=payload.status,
        artifact_summary_json=payload.artifact_summary_json,
        context_json=payload.context_json,
        tool_bundle_json=payload.tool_bundle_json,
        resume_context_json=payload.resume_context_json,
    )
    return run.model_dump()


@app.patch("/v1/agent-runs/{run_id}")
def update_agent_run_endpoint(
    run_id: int,
    payload: AgentRunUpdateRequest,
    _: None = Depends(require_control_api_token),
) -> dict:
    run = update_agent_run(
        run_id,
        payload.status,
        approved_by=payload.approved_by,
        completed_by=payload.completed_by,
        branch_name=payload.branch_name,
        pr_url=payload.pr_url,
        slack_channel_id=payload.slack_channel_id,
        slack_thread_ts=payload.slack_thread_ts,
        context_json=payload.context_json,
        tool_bundle_json=payload.tool_bundle_json,
        resume_context_json=payload.resume_context_json,
        error_message=payload.error_message,
        openclaw_session_id=payload.openclaw_session_id,
    )
    if not run:
        raise HTTPException(status_code=404, detail=f"Agent run {run_id} was not found.")
    return run.model_dump()


@app.post("/v1/agent-runs/{run_id}/artifacts")
def append_agent_run_artifact_endpoint(
    run_id: int,
    payload: AgentRunArtifactRequest,
    _: None = Depends(require_control_api_token),
) -> dict:
    run = append_agent_run_artifact(run_id, payload.artifact)
    if not run:
        raise HTTPException(status_code=404, detail=f"Agent run {run_id} was not found.")
    return run.model_dump()


@app.post("/v1/briefings/generate", status_code=201)
def generate_briefing_endpoint(payload: dict, _: None = Depends(require_control_api_token)) -> dict:
    briefing = generate_briefing(
        scope=payload.get("scope", "daily"),
        delivered_to=payload.get("delivered_to"),
    )
    return briefing.model_dump()


@app.post("/v1/worker/run-once", status_code=202)
def run_worker_once_endpoint(payload: dict | None = None, _: None = Depends(require_control_api_token)) -> dict:
    payload = payload or {}
    worker_id = payload.get("worker_id") or "studio-chief"
    poll_interval_seconds = int(payload.get("poll_interval_seconds") or 5)
    if not _worker_run_lock.acquire(blocking=False):
        return {
            "status": "already_running",
            "worker_id": worker_id,
            "last_result": getattr(app.state, "last_worker_result", None),
        }
    thread = Thread(
        target=_run_worker_pass,
        args=(worker_id, poll_interval_seconds),
        daemon=True,
    )
    try:
        thread.start()
    except Exception:
        _worker_run_lock.release()
        raise
    return {
        "status": "started",
        "worker_id": worker_id,
    }
