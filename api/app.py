"""Internal HTTP API for the control-plane services that OpenClaw will call."""

from __future__ import annotations

import os
from threading import Lock, Thread

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from models.control_plane import (
    append_agent_run_artifact,
    create_agent_run,
    get_task_control_state,
    list_agent_runs,
    list_attention_items,
    list_briefings,
    update_agent_run,
)
from models.knowledge import (
    create_task_from_workflow_recipe,
    create_workflow_recipe,
    list_memory_entries,
    list_workflow_recipes,
    upsert_memory_entry,
)
from models.task import complete_manual_verification, create_task, list_tasks, requeue_task
from services.approval_service import (
    ApprovalCreateRequest,
    ApprovalResolutionRequest,
    create_approval,
    get_pending_approvals,
    resolve_approval,
)
from services.apollo_sales_source import ApolloMissingApiKeyError, ApolloRateLimitError
from services.briefing_service import generate_briefing
from services.importance_service import BusinessSignalInput, record_business_signal
from services.policy_engine import PolicyEvaluationRequest
from services.policy_service import evaluate_and_record_policy
from services.signal_service import SignalInput, record_signal
from services.sales_agent_service import (
    SalesAgentSendModeRequest,
    SalesAgentService,
    SalesImportRequest,
    SalesSenderCreateRequest,
)
from services.sales_send_worker import SalesSendWorker
from services.task_runner import TaskRunner

app = FastAPI(title="AI Venture Studio Control API", version="0.1.0")
_worker_run_lock = Lock()
_sales_service = SalesAgentService()


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


class TaskCreateRequest(BaseModel):
    idea_id: int | None = None
    title: str
    description: str
    category: str
    target_repo: str | None = None
    venture: str | None = None
    requested_by: str | None = None
    slack_channel_id: str | None = None
    slack_thread_ts: str | None = None


class WorkflowRecipeCreateRequest(BaseModel):
    slug: str | None = None
    title: str
    summary: str
    category: str
    target_repo: str | None = None
    venture: str | None = None
    task_title_template: str | None = None
    task_description_template: str | None = None
    tags: list[str] | None = None
    created_by: str | None = None


class WorkflowRecipeRunRequest(BaseModel):
    request: str = ""
    variables: dict | None = None
    requested_by: str | None = None
    slack_channel_id: str | None = None
    slack_thread_ts: str | None = None


class ManualVerificationCompleteRequest(BaseModel):
    story_id: str | None = None
    note: str = "Manual verification completed."


class TaskRequeueRequest(BaseModel):
    note: str = "Task requeued from Paperclip."


class MemoryEntryCreateRequest(BaseModel):
    kind: str
    title: str
    body: str
    task_id: int | None = None
    target_repo: str | None = None
    venture: str | None = None
    tags: list[str] | None = None
    source_key: str | None = None
    created_by: str | None = None


class SalesAgentCreateRequest(BaseModel):
    name: str = "Tempa Sales Agent"
    venture: str = "tempa"


class SalesPersonalizeRequest(BaseModel):
    limit: int = Field(default=5, ge=1, le=25)


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


@app.post("/v1/intake/business-signals", status_code=201)
def create_business_signal_endpoint(payload: BusinessSignalInput, _: None = Depends(require_control_api_token)) -> dict:
    result = record_business_signal(payload)
    return {
        "decision": result["decision"],
        "signal": result["signal"].model_dump() if result["signal"] else None,
        "attention_item": result["attention_item"].model_dump() if result["attention_item"] else None,
        "deduped": result["deduped"],
    }


@app.get("/v1/attention")
def list_attention_endpoint(
    limit: int = 50,
    venture: str | None = None,
    _: None = Depends(require_control_api_token),
) -> dict[str, list[dict]]:
    items = list_attention_items(limit=limit, venture=venture)
    return {"items": [item.model_dump() for item in items]}


@app.get("/v1/tasks")
def list_tasks_endpoint(
    limit: int = 50,
    status: str | None = None,
    venture: str | None = None,
    requested_by: str | None = None,
    _: None = Depends(require_control_api_token),
) -> dict[str, list[dict]]:
    items = list_tasks(
        limit=limit,
        status=status,
        venture=venture,
        requested_by=requested_by,
    )
    return {"items": [item.model_dump() for item in items]}


@app.post("/v1/tasks", status_code=201)
def create_task_endpoint(payload: TaskCreateRequest, _: None = Depends(require_control_api_token)) -> dict:
    task = create_task(**payload.model_dump())
    return task.model_dump()


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


@app.post("/v1/tasks/{task_id}/manual-verification/complete")
def complete_manual_verification_endpoint(
    task_id: int,
    payload: ManualVerificationCompleteRequest,
    _: None = Depends(require_control_api_token),
) -> dict:
    try:
        task = complete_manual_verification(
            task_id=task_id,
            story_id=payload.story_id,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return task.model_dump()


@app.post("/v1/tasks/{task_id}/requeue")
def requeue_task_endpoint(
    task_id: int,
    payload: TaskRequeueRequest,
    _: None = Depends(require_control_api_token),
) -> dict:
    try:
        task = requeue_task(task_id, note=payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return task.model_dump()


@app.get("/v1/agent-runs")
def list_agent_runs_endpoint(
    limit: int = 50,
    task_id: int | None = None,
    run_kind: str | None = None,
    status: str | None = None,
    trigger_source: str | None = None,
    _: None = Depends(require_control_api_token),
) -> dict[str, list[dict]]:
    items = list_agent_runs(
        limit=limit,
        task_id=task_id,
        run_kind=run_kind,
        status=status,
        trigger_source=trigger_source,
    )
    return {"items": [item.model_dump() for item in items]}


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


@app.get("/v1/briefings")
def list_briefings_endpoint(
    limit: int = 20,
    scope: str | None = None,
    delivered_to: str | None = None,
    _: None = Depends(require_control_api_token),
) -> dict[str, list[dict]]:
    items = list_briefings(
        limit=limit,
        scope=scope,
        delivered_to=delivered_to,
    )
    return {"items": [item.model_dump() for item in items]}


@app.post("/v1/sales/agents", status_code=201)
def create_sales_agent_endpoint(
    payload: SalesAgentCreateRequest,
    _: None = Depends(require_control_api_token),
) -> dict:
    agent = _sales_service.create_agent(name=payload.name, venture=payload.venture)
    return agent.model_dump()


@app.get("/v1/sales/agents")
def list_sales_agents_endpoint(
    venture: str | None = None,
    _: None = Depends(require_control_api_token),
) -> dict[str, list[dict]]:
    return {"items": [agent.model_dump() for agent in _sales_service.list_agents(venture=venture)]}


@app.post("/v1/sales/agents/{agent_id}/import", status_code=201)
def import_sales_prospects_endpoint(
    agent_id: int,
    payload: SalesImportRequest,
    _: None = Depends(require_control_api_token),
) -> dict:
    try:
        result = _sales_service.import_prospects(agent_id, payload)
    except ApolloMissingApiKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ApolloRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump()


@app.post("/v1/sales/agents/{agent_id}/senders", status_code=201)
def create_sales_sender_endpoint(
    agent_id: int,
    payload: SalesSenderCreateRequest,
    _: None = Depends(require_control_api_token),
) -> dict:
    return _sales_service.create_sender(agent_id, payload)


@app.post("/v1/sales/agents/{agent_id}/request-live-approval", status_code=201)
def request_sales_live_approval_endpoint(
    agent_id: int,
    _: None = Depends(require_control_api_token),
) -> dict:
    try:
        return _sales_service.request_first_live_send_approval(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/sales/agents/{agent_id}/dry-run-summary")
def sales_dry_run_summary_endpoint(
    agent_id: int,
    limit: int = 25,
    _: None = Depends(require_control_api_token),
) -> dict:
    return _sales_service.dry_run_summary(agent_id, limit=limit).model_dump()


@app.post("/v1/sales/agents/{agent_id}/personalize", status_code=202)
def personalize_sales_prospects_endpoint(
    agent_id: int,
    payload: SalesPersonalizeRequest,
    _: None = Depends(require_control_api_token),
) -> dict:
    result = _sales_service.personalize_prospects(agent_id, limit=payload.limit)
    return result.model_dump()


@app.post("/v1/sales/agents/{agent_id}/send", status_code=202)
def send_sales_prospects_endpoint(
    agent_id: int,
    _: None = Depends(require_control_api_token),
) -> dict:
    result = SalesSendWorker().run_once(agent_id)
    return result.model_dump()


@app.post("/v1/sales/agents/{agent_id}/pause")
def pause_sales_agent_endpoint(agent_id: int, _: None = Depends(require_control_api_token)) -> dict:
    agent = _sales_service.pause_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Sales agent {agent_id} was not found.")
    return agent.model_dump()


@app.post("/v1/sales/agents/{agent_id}/resume")
def resume_sales_agent_endpoint(agent_id: int, _: None = Depends(require_control_api_token)) -> dict:
    agent = _sales_service.resume_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Sales agent {agent_id} was not found.")
    return agent.model_dump()


@app.post("/v1/sales/agents/{agent_id}/send-mode")
def set_sales_agent_send_mode_endpoint(
    agent_id: int,
    payload: SalesAgentSendModeRequest,
    _: None = Depends(require_control_api_token),
) -> dict:
    try:
        agent = _sales_service.set_send_mode(agent_id, payload.send_mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not agent:
        raise HTTPException(status_code=404, detail=f"Sales agent {agent_id} was not found.")
    return agent.model_dump()


@app.get("/v1/sales/prospects")
def list_sales_prospects_endpoint(
    agent_id: int | None = None,
    status: str | None = None,
    _: None = Depends(require_control_api_token),
) -> dict[str, list[dict]]:
    return {"items": _sales_service.list_prospects(agent_id=agent_id, status=status)}


@app.get("/v1/sales/messages")
def list_sales_messages_endpoint(
    agent_id: int | None = None,
    status: str | None = None,
    _: None = Depends(require_control_api_token),
) -> dict[str, list[dict]]:
    return {"items": _sales_service.list_messages(agent_id=agent_id, status=status)}


@app.get("/v1/sales/health")
def sales_health_endpoint(
    agent_id: int | None = None,
    _: None = Depends(require_control_api_token),
) -> dict:
    return _sales_service.health(agent_id=agent_id)


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


@app.get("/v1/workflows")
def list_workflows_endpoint(
    limit: int = 50,
    category: str | None = None,
    target_repo: str | None = None,
    _: None = Depends(require_control_api_token),
) -> dict[str, list[dict]]:
    workflows = list_workflow_recipes(limit=limit, category=category, target_repo=target_repo)
    return {"items": [workflow.model_dump() for workflow in workflows]}


@app.post("/v1/workflows", status_code=201)
def create_workflow_endpoint(
    payload: WorkflowRecipeCreateRequest,
    _: None = Depends(require_control_api_token),
) -> dict:
    try:
        workflow = create_workflow_recipe(
            slug=payload.slug,
            title=payload.title,
            summary=payload.summary,
            category=payload.category,
            target_repo=payload.target_repo,
            venture=payload.venture,
            task_title_template=payload.task_title_template,
            task_description_template=payload.task_description_template,
            tags=payload.tags,
            created_by=payload.created_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return workflow.model_dump()


@app.post("/v1/workflows/{slug}/tasks", status_code=201)
def create_task_from_workflow_endpoint(
    slug: str,
    payload: WorkflowRecipeRunRequest,
    _: None = Depends(require_control_api_token),
) -> dict:
    try:
        task = create_task_from_workflow_recipe(
            slug,
            request=payload.request,
            variables=payload.variables,
            requested_by=payload.requested_by,
            slack_channel_id=payload.slack_channel_id,
            slack_thread_ts=payload.slack_thread_ts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return task.model_dump()


@app.get("/v1/memory")
def list_memory_endpoint(
    limit: int = 50,
    kind: str | None = None,
    target_repo: str | None = None,
    venture: str | None = None,
    _: None = Depends(require_control_api_token),
) -> dict[str, list[dict]]:
    entries = list_memory_entries(limit=limit, kind=kind, target_repo=target_repo, venture=venture)
    return {"items": [entry.model_dump() for entry in entries]}


@app.post("/v1/memory", status_code=201)
def create_memory_endpoint(
    payload: MemoryEntryCreateRequest,
    _: None = Depends(require_control_api_token),
) -> dict:
    try:
        entry = upsert_memory_entry(
            kind=payload.kind,
            title=payload.title,
            body=payload.body,
            task_id=payload.task_id,
            target_repo=payload.target_repo,
            venture=payload.venture,
            tags=payload.tags,
            source_key=payload.source_key,
            created_by=payload.created_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return entry.model_dump()
