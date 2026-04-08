"""Policy engine for deciding whether risky actions are allowed, blocked, or approval-gated."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from config.constants import ALLOWED_REPOS

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

DEFAULT_NETWORK_POLICY = {
    "allow_hosts": ["127.0.0.1", "localhost"],
    "approval_hosts": ["github.com", "api.github.com"],
    "blocked_hosts": [],
    "blocked_by_default": True,
}

DEFAULT_APPROVAL_POLICY = {
    "read_only_actions": ["read", "task_lookup", "task_query", "repo_read", "test_run"],
    "mutating_actions": [
        "file_write",
        "git_push",
        "pull_request",
        "network_request",
        "destructive_shell",
        "secret_access",
    ],
    "approval_required_actions": ["git_push", "pull_request"],
    "blocked_actions": ["destructive_shell", "secret_access"],
}


class PolicyEvaluationRequest(BaseModel):
    task_id: int
    agent_run_id: int | None = None
    story_id: str | None = None
    agent_role: str
    tool_name: str | None = None
    action_type: str
    target_type: str | None = None
    target_host: str | None = None
    target_repo: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] | None = None


class PolicyEvaluationResult(BaseModel):
    decision: str
    policy_name: str
    reason: str
    approval_required: bool = False


def _load_json_config(filename: str, default: dict[str, Any]) -> dict[str, Any]:
    path = CONFIG_DIR / filename
    if not path.exists():
        return default
    return {**default, **json.loads(path.read_text())}


def _normalized_host(host: str | None) -> str | None:
    if not host:
        return None
    return host.strip().lower()


def evaluate_policy(request: PolicyEvaluationRequest) -> PolicyEvaluationResult:
    network_policy = _load_json_config("network_policy.json", DEFAULT_NETWORK_POLICY)
    approval_policy = _load_json_config("approval_policy.json", DEFAULT_APPROVAL_POLICY)
    action = request.action_type.strip().lower()
    role = request.agent_role.strip().lower()
    host = _normalized_host(request.target_host)

    if request.target_repo and request.target_repo not in ALLOWED_REPOS:
        return PolicyEvaluationResult(
            decision="block",
            policy_name="repo-allowlist",
            reason=f"Repo {request.target_repo} is not in the allowed list.",
        )

    if role in {"researcher", "reviewer"} and action in approval_policy["mutating_actions"]:
        return PolicyEvaluationResult(
            decision="block",
            policy_name="role-boundary",
            reason=f"{request.agent_role} is read-only for {action}.",
        )

    if action in approval_policy["blocked_actions"]:
        return PolicyEvaluationResult(
            decision="block",
            policy_name="blocked-action",
            reason=f"{action} is blocked by policy.",
        )

    if action == "network_request":
        if not host:
            return PolicyEvaluationResult(
                decision="block",
                policy_name="network-host-required",
                reason="Network requests must declare a target host.",
            )
        if host in network_policy["blocked_hosts"]:
            return PolicyEvaluationResult(
                decision="block",
                policy_name="network-blocklist",
                reason=f"{host} is blocked by network policy.",
            )
        if host in network_policy["allow_hosts"]:
            return PolicyEvaluationResult(
                decision="allow",
                policy_name="network-allowlist",
                reason=f"{host} is allowlisted.",
            )
        if host in network_policy["approval_hosts"]:
            return PolicyEvaluationResult(
                decision="require_approval",
                policy_name="network-approval",
                reason=f"{host} requires human approval.",
                approval_required=True,
            )
        if network_policy["blocked_by_default"]:
            return PolicyEvaluationResult(
                decision="block",
                policy_name="network-default-deny",
                reason=f"{host} is not on the allowlist.",
            )

    if action in approval_policy["approval_required_actions"]:
        return PolicyEvaluationResult(
            decision="require_approval",
            policy_name="approval-required",
            reason=f"{action} requires human approval.",
            approval_required=True,
        )

    return PolicyEvaluationResult(
        decision="allow",
        policy_name="default-allow",
        reason=f"{action} is allowed for {request.agent_role}.",
    )
