"""Business-signal filtering that decides what is worth routing into the control plane."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from services.signal_service import SignalInput, record_signal


class BusinessSignalInput(BaseModel):
    source: str
    category: str
    metric_name: str
    summary: str
    dedupe_key: str | None = None
    freshness_seconds: int | None = 86_400
    venture: str | None = None
    direction: str | None = None
    change_percent: float | None = None
    current_value: float | int | str | None = None
    previous_value: float | int | str | None = None
    urgency_hint: str | None = None
    task_id: int | None = None
    agent_run_id: int | None = None
    evidence_json: dict[str, Any] | None = None
    recommended_action: str | None = None
    slack_channel_id: str | None = None
    slack_thread_ts: str | None = None


class BusinessSignalDecision(BaseModel):
    should_record: bool
    kind: str
    severity: str
    bucket: str
    summary: str
    recommended_action: str
    reason: str


def _normalize(value: str | None, *, default: str = "") -> str:
    return (value or default).strip().lower()


def _infer_kind(category: str, direction: str, severity: str) -> str:
    if category in {"revenue", "payments", "billing", "cash"} and direction == "down":
        return "revenue_risk"
    if category in {"retention", "support", "customer", "churn"} and direction == "down":
        return "customer_risk"
    if category in {"growth", "sales", "pipeline"} and direction == "down":
        return "growth_risk"
    if category in {"growth", "sales", "pipeline"} and direction == "up":
        return "growth_opportunity"
    if category in {"usage", "product", "adoption"} and direction == "up":
        return "usage_trend"
    if category in {"usage", "product", "adoption"} and direction == "down":
        return "usage_risk"
    if severity in {"critical", "high"}:
        return "business_risk"
    return "business_trend"


def _decide_severity(category: str, direction: str, change_percent: float | None, urgency_hint: str) -> tuple[str, str]:
    if urgency_hint in {"critical", "high"}:
        return urgency_hint, f"Caller marked this as {urgency_hint} urgency."

    abs_change = abs(change_percent or 0.0)
    if direction == "flat" and abs_change < 5:
        return "low", "Movement is too small to matter."

    if category in {"revenue", "payments", "billing", "cash"}:
        if direction == "down" and abs_change >= 20:
            return "critical", "Revenue or cash moved down sharply."
        if direction == "down" and abs_change >= 10:
            return "high", "Revenue or cash moved down enough to need attention."
        if direction == "up" and abs_change >= 10:
            return "normal", "Revenue improved enough to mention in a brief."
        return "low", "Revenue movement is minor."

    if category in {"retention", "support", "customer", "churn"}:
        if direction == "down" and abs_change >= 10:
            return "high", "Customer health worsened enough to need attention."
        if direction == "up" and abs_change >= 10:
            return "normal", "Customer health improved enough to mention in a brief."
        return "low", "Customer signal is minor."

    if category in {"growth", "sales", "pipeline"}:
        if direction == "down" and abs_change >= 15:
            return "high", "Growth slipped enough to deserve attention."
        if direction == "up" and abs_change >= 10:
            return "normal", "Growth improved enough to mention in a brief."
        return "low", "Growth movement is minor."

    if category in {"usage", "product", "adoption"}:
        if direction == "down" and abs_change >= 20:
            return "high", "Product usage dropped sharply."
        if direction == "up" and abs_change >= 15:
            return "normal", "Product usage improved enough to mention in a brief."
        return "low", "Usage movement is minor."

    if direction == "down" and abs_change >= 15:
        return "high", "A business metric moved down sharply."
    if abs_change >= 10:
        return "normal", "A business metric moved enough to mention in a brief."
    return "low", "Movement is too small to route upward."


def evaluate_business_signal(signal_input: BusinessSignalInput) -> BusinessSignalDecision:
    category = _normalize(signal_input.category)
    direction = _normalize(signal_input.direction, default="flat")
    urgency_hint = _normalize(signal_input.urgency_hint)
    severity, reason = _decide_severity(category, direction, signal_input.change_percent, urgency_hint)
    kind = _infer_kind(category, direction, severity)

    if severity == "low":
        return BusinessSignalDecision(
            should_record=False,
            kind=kind,
            severity=severity,
            bucket="ignore",
            summary=signal_input.summary,
            recommended_action="Do not route this upward unless it persists.",
            reason=reason,
        )

    if severity in {"critical", "high"}:
        return BusinessSignalDecision(
            should_record=True,
            kind=kind,
            severity=severity,
            bucket="notify",
            summary=signal_input.summary,
            recommended_action=signal_input.recommended_action
            or "Surface this to the founder now and create follow-up work if needed.",
            reason=reason,
        )

    return BusinessSignalDecision(
        should_record=True,
        kind=kind,
        severity="normal",
        bucket="digest",
        summary=signal_input.summary,
        recommended_action=signal_input.recommended_action or "Include this in the next founder brief.",
        reason=reason,
    )


def record_business_signal(signal_input: BusinessSignalInput) -> dict[str, Any]:
    decision = evaluate_business_signal(signal_input)
    if not decision.should_record:
        return {
            "decision": decision.model_dump(),
            "signal": None,
            "attention_item": None,
            "deduped": False,
        }

    details_json = {
        "category": signal_input.category,
        "metric_name": signal_input.metric_name,
        "direction": signal_input.direction,
        "change_percent": signal_input.change_percent,
        "current_value": signal_input.current_value,
        "previous_value": signal_input.previous_value,
        "reason": decision.reason,
        "recommended_action": decision.recommended_action,
        "evidence": signal_input.evidence_json or {},
    }

    recorded = record_signal(
        SignalInput(
            source=signal_input.source,
            kind=decision.kind,
            task_id=signal_input.task_id,
            agent_run_id=signal_input.agent_run_id,
            venture=signal_input.venture,
            severity=decision.severity,
            summary=decision.summary,
            details_json=details_json,
            dedupe_key=signal_input.dedupe_key,
            freshness_seconds=signal_input.freshness_seconds,
            recommended_action=decision.recommended_action,
            slack_channel_id=signal_input.slack_channel_id,
            slack_thread_ts=signal_input.slack_thread_ts,
        )
    )
    return {"decision": decision.model_dump(), **recorded}
