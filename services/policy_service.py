"""Policy orchestration that records decisions and creates approval/attention records."""

from __future__ import annotations

from pydantic import BaseModel

from models.control_plane import create_policy_decision
from services.approval_service import ApprovalCreateRequest, create_approval
from services.policy_engine import PolicyEvaluationRequest, evaluate_policy
from services.signal_service import SignalInput, record_signal


class RecordedPolicyEvaluation(BaseModel):
    decision: str
    policy_name: str
    reason: str
    approval_required: bool = False
    policy_decision_id: int | None = None
    approval_request_id: int | None = None
    signal_id: int | None = None
    attention_item_id: int | None = None


def _target_summary(request: PolicyEvaluationRequest) -> str:
    if request.target_repo:
        return f"{request.action_type} on repo {request.target_repo}"
    if request.target_host:
        return f"{request.action_type} to host {request.target_host}"
    return request.action_type


def evaluate_and_record_policy(request: PolicyEvaluationRequest) -> RecordedPolicyEvaluation:
    result = evaluate_policy(request)
    approval = None
    signal_result = None

    if result.decision == "require_approval":
        approval = create_approval(
            ApprovalCreateRequest(
                task_id=request.task_id,
                agent_run_id=request.agent_run_id,
                action_type=request.action_type,
                target_summary=_target_summary(request),
                external_event_id=(
                    f"{request.task_id}:{request.agent_run_id or 'no-run'}:{request.action_type}:"
                    f"{request.target_host or request.target_repo or 'general'}"
                ),
            )
        )
        signal_result = record_signal(
            SignalInput(
                source="policy-engine",
                kind="approval_required",
                task_id=request.task_id,
                agent_run_id=request.agent_run_id,
                severity="high",
                summary=f"Approval required for {_target_summary(request)}",
                details_json=request.model_dump(),
                recommended_action="Review and approve or deny this request in Slack.",
            )
        )
    elif result.decision == "block":
        signal_result = record_signal(
            SignalInput(
                source="policy-engine",
                kind="policy_blocked",
                task_id=request.task_id,
                agent_run_id=request.agent_run_id,
                severity="critical",
                summary=f"Blocked {_target_summary(request)}",
                details_json=request.model_dump(),
                recommended_action="Review the blocked action and adjust policy only if intended.",
            )
        )

    policy_decision = create_policy_decision(
        task_id=request.task_id,
        action_type=request.action_type,
        decision=result.decision,
        policy_name=result.policy_name,
        reason=result.reason,
        agent_run_id=request.agent_run_id,
        story_id=request.story_id,
        tool_name=request.tool_name,
        target_type=request.target_type,
        target_host=request.target_host,
        target_repo=request.target_repo,
        approval_request_id=approval.id if approval else None,
    )

    return RecordedPolicyEvaluation(
        decision=result.decision,
        policy_name=result.policy_name,
        reason=result.reason,
        approval_required=result.approval_required,
        policy_decision_id=policy_decision.id,
        approval_request_id=approval.id if approval else None,
        signal_id=signal_result["signal"].id if signal_result and signal_result["signal"] else None,
        attention_item_id=(
            signal_result["attention_item"].id
            if signal_result and signal_result["attention_item"]
            else None
        ),
    )
