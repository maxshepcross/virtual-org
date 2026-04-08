"""Internal HTTP API for the control-plane services that OpenClaw will call."""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException

from models.control_plane import (
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
from services.signal_service import SignalInput, record_signal

app = FastAPI(title="AI Venture Studio Control API", version="0.1.0")


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
    approval = create_approval(payload)
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
def create_agent_run_endpoint(payload: dict, _: None = Depends(require_control_api_token)) -> dict:
    run = create_agent_run(
        task_id=payload.get("task_id"),
        story_id=payload.get("story_id"),
        agent_class=payload["agent_class"],
        agent_role=payload["agent_role"],
        openclaw_session_id=payload.get("openclaw_session_id"),
        status=payload.get("status", "running"),
        resume_context_json=payload.get("resume_context_json"),
    )
    return run.model_dump()


@app.patch("/v1/agent-runs/{run_id}")
def update_agent_run_endpoint(run_id: int, payload: dict, _: None = Depends(require_control_api_token)) -> dict:
    run = update_agent_run(
        run_id,
        payload["status"],
        resume_context_json=payload.get("resume_context_json"),
        error_message=payload.get("error_message"),
        openclaw_session_id=payload.get("openclaw_session_id"),
    )
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
