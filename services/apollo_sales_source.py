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
