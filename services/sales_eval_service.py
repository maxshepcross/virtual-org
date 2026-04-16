"""Layered quality checks for Tempa sales personalization."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from pydantic import BaseModel, Field


REQUIRED_STRATEGY_FIELDS = {
    "company",
    "prospect",
    "evidence_urls",
    "observed_growth_context",
    "suggested_paid_social_angle",
    "target_audience",
    "example_ad_concept",
    "why_tempa_can_help",
    "confidence_score",
}

BANNED_PHRASES = {
    "guaranteed",
    "i loved your",
    "huge fan",
    "we noticed your revenue",
    "your revenue is",
}


class SalesEvalInput(BaseModel):
    strategy_json: dict
    email_subject: str
    email_body: str
    postal_address: str | None = None
    unsubscribe_link: str | None = None
    max_email_chars: int = 1800


class SalesEvalOutput(BaseModel):
    passed: bool
    deterministic_passed: bool
    llm_passed: bool | None = None
    failures: list[str] = Field(default_factory=list)


class SalesEvalService:
    def evaluate(self, payload: SalesEvalInput) -> SalesEvalOutput:
        failures = self._deterministic_failures(payload)
        deterministic_passed = not failures
        # V0 records deterministic pass separately. Live sending is still blocked
        # unless a real LLM rubric later writes llm_passed=True to the eval row.
        llm_passed = None
        return SalesEvalOutput(
            passed=deterministic_passed,
            deterministic_passed=deterministic_passed,
            llm_passed=llm_passed,
            failures=failures,
        )

    def _deterministic_failures(self, payload: SalesEvalInput) -> list[str]:
        failures: list[str] = []
        strategy = payload.strategy_json
        missing = sorted(field for field in REQUIRED_STRATEGY_FIELDS if field not in strategy)
        if missing:
            failures.append(f"missing required strategy fields: {', '.join(missing)}")

        evidence_urls = strategy.get("evidence_urls")
        if not isinstance(evidence_urls, list) or not evidence_urls:
            failures.append("missing evidence_urls")
        else:
            for url in evidence_urls:
                parsed = urlparse(str(url))
                if parsed.scheme != "https" or not parsed.netloc:
                    failures.append("evidence_urls must contain valid HTTPS URLs")
                    break

        confidence = strategy.get("confidence_score")
        if not isinstance(confidence, int | float) or confidence < 0.8:
            failures.append("confidence_score must be at least 0.8")

        body_lower = payload.email_body.lower()
        subject_lower = payload.email_subject.lower()
        for phrase in BANNED_PHRASES:
            if phrase in body_lower or phrase in subject_lower:
                failures.append(f"banned phrase found: {phrase}")

        if len(payload.email_body) > payload.max_email_chars:
            failures.append("email body is too long")
        if "unsubscribe:" not in body_lower or not payload.unsubscribe_link:
            failures.append("unsubscribe link is required")
        elif not self._is_https_url(payload.unsubscribe_link):
            failures.append("unsubscribe link must be HTTPS")
        if not payload.postal_address:
            failures.append("postal address is required")
        if "re:" in subject_lower and "paid social idea" not in subject_lower:
            failures.append("subject may be misleading")
        unsupported_numeric_claims = self._unsupported_numeric_claims(payload.email_body, strategy)
        if unsupported_numeric_claims:
            failures.append("invented numeric claim found")
        return failures

    def _is_https_url(self, value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme == "https" and bool(parsed.netloc)

    def _unsupported_numeric_claims(self, email_body: str, strategy: dict) -> list[str]:
        strategy_text = json.dumps(strategy).lower()
        claims = re.findall(
            r"\b\d+(?:\.\d+)?\s?(?:%|percent\b|x\b|k\b|m\b|million\b|billion\b|users\b|revenue\b)",
            email_body.lower(),
        )
        return [claim for claim in claims if claim not in strategy_text]
