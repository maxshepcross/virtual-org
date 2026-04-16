"""Tempa mini-strategy client and email draft builder."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import httpx

from models.sales import SalesProspect


class TempaPersonalizationClient:
    def __init__(self, *, url: str | None = None, timeout_seconds: float = 30.0) -> None:
        self.url = url if url is not None else os.getenv("TEMPA_SALES_STRATEGY_URL", "").strip()
        self.timeout_seconds = timeout_seconds

    def create_strategy(self, prospect: SalesProspect) -> dict[str, Any]:
        if not self.url:
            raise RuntimeError("TEMPA_SALES_STRATEGY_URL is not configured.")
        self._validate_strategy_url()
        response = httpx.post(
            self.url,
            json={
                "company_name": prospect.company_name,
                "company_domain": prospect.company_domain,
                "company_url": prospect.company_url,
                "prospect_name": " ".join(part for part in [prospect.first_name, prospect.last_name] if part),
                "prospect_title": prospect.title,
                "source_context": prospect.source_context_json,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Tempa strategy response must be a JSON object.")
        return payload

    def _validate_strategy_url(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise RuntimeError("TEMPA_SALES_STRATEGY_URL must be an HTTPS URL.")
        allowed_hosts = {
            host.strip().lower()
            for host in os.getenv("TEMPA_SALES_STRATEGY_ALLOWED_HOSTS", "").split(",")
            if host.strip()
        }
        if allowed_hosts and parsed.hostname.lower() not in allowed_hosts:
            raise RuntimeError("TEMPA_SALES_STRATEGY_URL host is not allowed.")


def build_sales_email(
    *,
    prospect: SalesProspect,
    strategy: dict[str, Any],
    preview_link: str,
    unsubscribe_link: str,
    booking_link: str,
    sender_name: str,
    postal_address: str,
) -> tuple[str, str]:
    subject = f"Paid social idea for {prospect.company_name}"
    first_name = prospect.first_name or "there"
    body = f"""Hi {first_name},

I was looking at {prospect.company_name} and noticed {strategy.get("observed_growth_context", "a few growth signals worth testing")}.

I put together one paid-social angle I'd test:
{preview_link}

Short version:
- Audience: {strategy.get("target_audience", "")}
- Hook: {strategy.get("suggested_paid_social_angle", "")}

Worth a quick demo next week?
{booking_link}

{sender_name}
{postal_address}
Unsubscribe: {unsubscribe_link}
"""
    return subject, body
