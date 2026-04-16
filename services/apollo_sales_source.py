"""Apollo prospect source for the Tempa sales experiment.

Uses Apollo's People API Search endpoint:
https://docs.apollo.io/reference/people-api-search
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic import BaseModel, Field


APOLLO_PEOPLE_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_people/api_search"


class ApolloSearchRequest(BaseModel):
    person_titles: list[str] = Field(default_factory=lambda: ["founder", "co-founder", "ceo"])
    person_locations: list[str] = Field(default_factory=lambda: ["United States"])
    organization_locations: list[str] | None = None
    per_page: int = 25
    page: int = 1
    min_signal_score: int = Field(default=0, ge=0, le=100)
    signal_keywords: list[str] = Field(
        default_factory=lambda: [
            "growth",
            "marketing",
            "paid social",
            "ecommerce",
            "saas",
            "software",
            "startup",
        ]
    )


class ApolloLeadSignal(BaseModel):
    score: int
    tier: str
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ApolloSalesSourceError(RuntimeError):
    """Base error for Apollo sourcing failures."""


class ApolloMissingApiKeyError(ApolloSalesSourceError):
    """Raised when Apollo import is requested without an API key."""


class ApolloRateLimitError(ApolloSalesSourceError):
    """Raised when Apollo returns a rate-limit response."""


class ApolloSalesSource:
    def __init__(self, *, api_key: str | None = None, timeout_seconds: float = 20.0) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("APOLLO_API_KEY", "").strip()
        self.timeout_seconds = timeout_seconds

    def search_people(self, request: ApolloSearchRequest) -> list[dict[str, Any]]:
        if not self.api_key:
            raise ApolloMissingApiKeyError("APOLLO_API_KEY is not configured.")
        per_page = max(1, min(request.per_page, 25))
        params: dict[str, Any] = {
            "person_titles[]": request.person_titles,
            "person_locations[]": request.person_locations,
            "per_page": per_page,
            "page": request.page,
        }
        if request.organization_locations:
            params["organization_locations[]"] = request.organization_locations

        response = httpx.post(
            APOLLO_PEOPLE_SEARCH_URL,
            params=params,
            headers={
                "accept": "application/json",
                "cache-control": "no-cache",
                "content-type": "application/json",
                "x-api-key": self.api_key,
            },
            timeout=self.timeout_seconds,
        )
        if response.status_code == 429:
            raise ApolloRateLimitError("Apollo rate limit reached.")
        response.raise_for_status()
        payload = response.json()
        return payload.get("people") or []


def score_apollo_lead(person: dict[str, Any], *, signal_keywords: list[str] | None = None) -> ApolloLeadSignal:
    organization = person.get("organization") if isinstance(person.get("organization"), dict) else {}
    title = str(person.get("title") or "").lower()
    company_name = str(
        person.get("organization_name")
        or organization.get("name")
        or person.get("company")
        or person.get("company_name")
        or ""
    ).strip()
    company_domain = (
        person.get("organization_primary_domain")
        or organization.get("primary_domain")
        or organization.get("website_url")
        or person.get("company_domain")
    )
    email = str(person.get("email") or "").strip()
    reasons: list[str] = []
    warnings: list[str] = []
    score = 0

    if any(term in title for term in ("founder", "co-founder", "ceo", "owner")):
        score += 35
        reasons.append("senior founder/operator title")
    elif any(term in title for term in ("growth", "marketing", "demand generation", "performance")):
        score += 25
        reasons.append("growth or marketing title")
    elif title:
        score += 10
        reasons.append("named professional title")
    else:
        warnings.append("missing title")

    if company_name:
        score += 10
        reasons.append("company name present")
    else:
        warnings.append("missing company")

    if company_domain:
        score += 20
        reasons.append("company website/domain present")
    else:
        warnings.append("missing company domain")

    employee_count = _employee_count(person, organization)
    if employee_count is not None:
        if 2 <= employee_count <= 250:
            score += 15
            reasons.append("company size fits early growth test")
        elif employee_count > 1000:
            score -= 10
            warnings.append("company may be too large for this wedge")

    keyword_text = _keyword_text(person, organization)
    matched_keywords = [
        keyword
        for keyword in (signal_keywords or [])
        if keyword.strip() and keyword.strip().lower() in keyword_text
    ]
    if matched_keywords:
        score += 20
        reasons.append(f"matched signal keywords: {', '.join(matched_keywords[:5])}")

    if not email or "@" not in email:
        warnings.append("missing email")

    bounded_score = max(0, min(100, score))
    if bounded_score >= 70:
        tier = "high"
    elif bounded_score >= 45:
        tier = "medium"
    else:
        tier = "low"
    return ApolloLeadSignal(score=bounded_score, tier=tier, reasons=reasons, warnings=warnings)


def _employee_count(person: dict[str, Any], organization: dict[str, Any]) -> int | None:
    for key in ("estimated_num_employees", "employee_count", "employees"):
        value = organization.get(key) or person.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _keyword_text(person: dict[str, Any], organization: dict[str, Any]) -> str:
    pieces: list[str] = []
    for source in (person, organization):
        for key in ("headline", "industry", "keywords", "short_description", "seo_description", "languages"):
            value = source.get(key)
            if isinstance(value, str):
                pieces.append(value)
            elif isinstance(value, list):
                pieces.extend(str(item) for item in value)
    return " ".join(pieces).lower()
