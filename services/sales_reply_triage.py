"""Classify replies without sending automated responses."""

from __future__ import annotations

from pydantic import BaseModel


TRIAGE_CLASSIFICATIONS = {"positive", "neutral", "objection", "unsubscribe", "angry", "unknown"}


class ReplyTriageResult(BaseModel):
    classification: str
    suggested_response_angle: str | None = None
    model_output_json: dict | None = None


class SalesReplyTriage:
    def classify(self, text: str | None) -> ReplyTriageResult:
        cleaned = (text or "").strip().lower()
        if not cleaned:
            return ReplyTriageResult(classification="unknown", suggested_response_angle="Review the reply manually.")
        if any(word in cleaned for word in ("unsubscribe", "remove me", "stop emailing")):
            return ReplyTriageResult(classification="unsubscribe")
        if any(word in cleaned for word in ("angry", "spam", "report", "never email")):
            return ReplyTriageResult(classification="angry", suggested_response_angle="Do not reply. Suppress and review sender health.")
        if any(word in cleaned for word in ("interested", "book", "demo", "next week", "tell me more")):
            return ReplyTriageResult(classification="positive", suggested_response_angle="Offer two specific demo times.")
        if any(word in cleaned for word in ("not now", "too expensive", "already use", "no budget")):
            return ReplyTriageResult(classification="objection", suggested_response_angle="Acknowledge the objection and ask one qualifying question.")
        return ReplyTriageResult(classification="neutral", suggested_response_angle="Ask whether the paid-social angle is relevant.")
