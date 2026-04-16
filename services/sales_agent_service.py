"""Workflow owner for the Tempa sales agent.

Other sales services return data. This service owns workflow state changes.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from models.sales import (
    SalesAgent,
    create_sender_account,
    create_outreach_message,
    create_personalization,
    create_prospect,
    create_sales_agent,
    get_sales_agent,
    get_latest_eval_result,
    get_personalization,
    get_prospect,
    list_sales_agents,
    list_sales_messages,
    list_sales_prospects,
    list_sender_accounts,
    record_eval_result,
    set_sales_agent_send_mode,
    set_sales_agent_status,
    transition_prospect_status,
)
from services.approval_service import ExternalApprovalCreateRequest, create_external_approval
from services.apollo_sales_source import ApolloLeadSignal, ApolloSalesSource, ApolloSearchRequest, score_apollo_lead
from services.sales_eval_service import SalesEvalInput, SalesEvalService
from services.sales_approval_keys import sales_message_approval_event_id
from services.sales_personalization import TempaPersonalizationClient, build_sales_email
from services.sales_preview_service import SalesPreviewService
from services.sales_sender_health import SalesSenderHealthService


logger = logging.getLogger(__name__)


class SalesProspectImportInput(BaseModel):
    email: str
    company_name: str
    first_name: str | None = None
    last_name: str | None = None
    title: str | None = None
    company_domain: str | None = None
    company_url: str | None = None
    country: str | None = "US"
    external_id: str | None = None
    source_context_json: dict[str, Any] | None = None


class SalesImportRequest(BaseModel):
    source: str = "manual_seed"
    prospects: list[SalesProspectImportInput] = Field(default_factory=list)
    apollo_search: ApolloSearchRequest | None = None


class SalesImportResult(BaseModel):
    imported: int
    skipped_duplicates: int
    skipped_invalid: int = 0
    returned: int = 0
    skipped_low_signal: int = 0
    missing_email: int = 0
    missing_company: int = 0
    invalid_country: int = 0


class SalesPersonalizeResult(BaseModel):
    personalized: int
    eval_failed: int
    failed: int


class SalesSenderCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    inbox_id: str
    daily_cap: int = Field(default=5, ge=1, le=20)


class SalesAgentSendModeRequest(BaseModel):
    send_mode: str


class SalesDryRunSummaryItem(BaseModel):
    message_id: int | None
    prospect_id: int | None
    company_name: str
    prospect_name: str | None = None
    prospect_title: str | None = None
    company_domain: str | None = None
    country: str | None = None
    subject: str
    email_body: str
    preview_link: str | None = None
    eval_status: str | None = None
    eval_failures: list[str] = Field(default_factory=list)
    passed_reasons: list[str] = Field(default_factory=list)


class SalesDryRunSummary(BaseModel):
    agent_id: int
    ready_count: int
    blocked_count: int
    send_mode: str
    kill_switch: bool
    first_live_approval_status: str
    items: list[SalesDryRunSummaryItem]


class SalesAgentService:
    def __init__(
        self,
        *,
        personalization_client: TempaPersonalizationClient | None = None,
        eval_service: SalesEvalService | None = None,
        preview_service: SalesPreviewService | None = None,
        apollo_source: ApolloSalesSource | None = None,
        sender_health_service: SalesSenderHealthService | None = None,
    ) -> None:
        self.personalization_client = personalization_client or TempaPersonalizationClient()
        self.eval_service = eval_service or SalesEvalService()
        self.preview_service = preview_service or SalesPreviewService()
        self.apollo_source = apollo_source or ApolloSalesSource()
        self.sender_health_service = sender_health_service or SalesSenderHealthService()

    def create_agent(self, *, name: str = "Tempa Sales Agent", venture: str = "tempa") -> SalesAgent:
        limit = int(os.getenv("SALES_DAILY_NEW_PROSPECT_LIMIT", "5") or "5")
        agent = create_sales_agent(
            name=name,
            venture=venture,
            status="paused",
            send_mode=os.getenv("SALES_SEND_MODE", "dry_run") or "dry_run",
            daily_new_prospect_limit=limit,
        )
        logger.info(
            "sales_agent_created",
            extra={"agent_id": agent.id, "venture": agent.venture, "send_mode": agent.send_mode, "daily_limit": limit},
        )
        return agent

    def list_agents(self, *, venture: str | None = None) -> list[SalesAgent]:
        return list_sales_agents(venture=venture)

    def pause_agent(self, agent_id: int) -> SalesAgent | None:
        agent = set_sales_agent_status(agent_id, "paused")
        logger.info("sales_agent_paused", extra={"agent_id": agent_id, "updated": bool(agent)})
        return agent

    def resume_agent(self, agent_id: int) -> SalesAgent | None:
        agent = set_sales_agent_status(agent_id, "active")
        logger.info("sales_agent_resumed", extra={"agent_id": agent_id, "updated": bool(agent)})
        return agent

    def set_send_mode(self, agent_id: int, send_mode: str) -> SalesAgent | None:
        agent = set_sales_agent_send_mode(agent_id, send_mode)
        logger.info("sales_agent_send_mode_set", extra={"agent_id": agent_id, "send_mode": send_mode, "updated": bool(agent)})
        return agent

    def create_sender(self, agent_id: int, request: SalesSenderCreateRequest) -> dict:
        sender = create_sender_account(
            agent_id=agent_id,
            email=request.email,
            inbox_id=request.inbox_id,
            status="paused",
            daily_cap=request.daily_cap,
            verified=False,
        )
        return sender.model_dump()

    def request_first_live_send_approval(self, agent_id: int) -> dict:
        agent = get_sales_agent(agent_id)
        if not agent:
            raise ValueError(f"Sales agent {agent_id} was not found.")
        summary = self.dry_run_summary(agent_id)
        if summary.ready_count < 1:
            raise ValueError("Cannot request live approval before at least one message has passed review.")
        if summary.blocked_count:
            raise ValueError("Cannot request live approval while reviewed messages are blocked.")
        item = next((item for item in summary.items if item.message_id), None)
        if not item:
            raise ValueError("Cannot request live approval without a concrete message to approve.")
        approval_event_id = sales_message_approval_event_id(
            agent_id=agent_id,
            message_id=item.message_id,
            subject=item.subject,
            body=item.email_body,
        )
        logger.info(
            "sales_live_approval_requested",
            extra={
                "agent_id": agent_id,
                "message_id": item.message_id,
                "ready_count": summary.ready_count,
                "blocked_count": summary.blocked_count,
            },
        )
        approval = create_external_approval(
            ExternalApprovalCreateRequest(
                action_type="sales_first_live_send",
                target_summary=(
                    f"Approve exact first live Tempa sales message {item.message_id} for sales agent {agent_id}. "
                    f"Ready messages: {summary.ready_count}. Blocked messages: {summary.blocked_count}. "
                    f"Company: {item.company_name}. Subject: {item.subject}. "
                    "This unlocks this message only after all other sender and compliance checks pass."
                ),
                external_event_id=approval_event_id,
            )
        )
        return approval.model_dump()

    def import_prospects(self, agent_id: int, request: SalesImportRequest) -> SalesImportResult:
        logger.info("sales_import_started", extra={"agent_id": agent_id, "source": request.source})
        if request.source == "apollo":
            result = self._import_from_apollo(agent_id, request.apollo_search or ApolloSearchRequest())
        elif request.source == "manual_seed":
            result = self._import_manual_prospects(agent_id, request.source, request.prospects)
        else:
            raise ValueError("Sales import source must be 'manual_seed' or 'apollo'.")
        logger.info(
            "sales_import_finished",
            extra={
                "agent_id": agent_id,
                "source": request.source,
                "imported": result.imported,
                "skipped_duplicates": result.skipped_duplicates,
                "skipped_invalid": result.skipped_invalid,
                "returned": result.returned,
                "skipped_low_signal": result.skipped_low_signal,
                "missing_email": result.missing_email,
                "missing_company": result.missing_company,
                "invalid_country": result.invalid_country,
            },
        )
        return result

    def _import_manual_prospects(
        self,
        agent_id: int,
        source: str,
        prospects: list[SalesProspectImportInput],
    ) -> SalesImportResult:
        imported = 0
        skipped = 0
        skipped_invalid = 0
        for prospect in prospects:
            if not self._valid_import_prospect(prospect):
                skipped_invalid += 1
                continue
            created = create_prospect(
                agent_id=agent_id,
                source=source,
                external_id=prospect.external_id,
                email=prospect.email,
                first_name=prospect.first_name,
                last_name=prospect.last_name,
                title=prospect.title,
                company_name=prospect.company_name,
                company_domain=prospect.company_domain,
                company_url=prospect.company_url,
                country=prospect.country,
                source_context_json=prospect.source_context_json,
            )
            if created:
                imported += 1
            else:
                skipped += 1
        return SalesImportResult(imported=imported, skipped_duplicates=skipped, skipped_invalid=skipped_invalid)

    def _import_from_apollo(self, agent_id: int, search: ApolloSearchRequest) -> SalesImportResult:
        raw_people = self.apollo_source.search_people(search)
        imported = 0
        skipped_duplicates = 0
        skipped_invalid = 0
        skipped_low_signal = 0
        missing_email = 0
        missing_company = 0
        invalid_country = 0

        for person in raw_people:
            signal = score_apollo_lead(person, signal_keywords=search.signal_keywords)
            if signal.score < search.min_signal_score:
                skipped_low_signal += 1
                continue
            prospect, invalid_reasons = self._apollo_person_to_import(person, signal)
            if invalid_reasons:
                skipped_invalid += 1
                if "missing_email" in invalid_reasons:
                    missing_email += 1
                if "missing_company" in invalid_reasons:
                    missing_company += 1
                continue
            if not prospect:
                skipped_invalid += 1
                continue
            if not self._valid_import_prospect(prospect):
                skipped_invalid += 1
                invalid_country += 1
                continue
            created = create_prospect(
                agent_id=agent_id,
                source="apollo",
                external_id=prospect.external_id,
                email=prospect.email,
                first_name=prospect.first_name,
                last_name=prospect.last_name,
                title=prospect.title,
                company_name=prospect.company_name,
                company_domain=prospect.company_domain,
                company_url=prospect.company_url,
                country=prospect.country,
                source_context_json=prospect.source_context_json,
            )
            if created:
                imported += 1
            else:
                skipped_duplicates += 1

        return SalesImportResult(
            imported=imported,
            skipped_duplicates=skipped_duplicates,
            skipped_invalid=skipped_invalid,
            returned=len(raw_people),
            skipped_low_signal=skipped_low_signal,
            missing_email=missing_email,
            missing_company=missing_company,
            invalid_country=invalid_country,
        )

    def _apollo_person_to_import(
        self,
        person: dict[str, Any],
        signal: ApolloLeadSignal,
    ) -> tuple[SalesProspectImportInput | None, list[str]]:
        email = str(person.get("email") or "").strip()
        organization = person.get("organization") if isinstance(person.get("organization"), dict) else {}
        company_name = (
            person.get("organization_name")
            or organization.get("name")
            or person.get("company")
            or person.get("company_name")
            or ""
        )
        company_name = str(company_name).strip()
        invalid_reasons: list[str] = []
        if not email or "@" not in email:
            invalid_reasons.append("missing_email")
        if not company_name:
            invalid_reasons.append("missing_company")
        if invalid_reasons:
            return None, invalid_reasons

        company_domain = (
            person.get("organization_primary_domain")
            or organization.get("primary_domain")
            or organization.get("website_url")
            or person.get("company_domain")
        )
        return SalesProspectImportInput(
            email=email,
            company_name=company_name,
            first_name=person.get("first_name"),
            last_name=person.get("last_name"),
            title=person.get("title"),
            company_domain=self._domain_from_value(company_domain),
            company_url=organization.get("website_url") or person.get("company_url"),
            country=person.get("country") or person.get("person_country") or "US",
            external_id=person.get("id"),
            source_context_json={
                "apollo": self._safe_apollo_context(person),
                "lead_signal": signal.model_dump(),
            },
        ), []

    def _valid_import_prospect(self, prospect: SalesProspectImportInput) -> bool:
        if not prospect.email or "@" not in prospect.email or not prospect.company_name.strip():
            return False
        allowed_countries = {
            country.strip().upper()
            for country in os.getenv("SALES_ALLOWED_RECIPIENT_COUNTRIES", "US").split(",")
            if country.strip()
        }
        if allowed_countries and (prospect.country or "").strip().upper() not in allowed_countries:
            return False
        return True

    def _domain_from_value(self, value: Any) -> str | None:
        if not value:
            return None
        raw = str(value).strip().lower()
        if not raw:
            return None
        if "://" not in raw:
            raw = f"https://{raw}"
        parsed = urlparse(raw)
        return parsed.netloc.removeprefix("www.") or None

    def _safe_apollo_context(self, person: dict[str, Any]) -> dict[str, Any]:
        organization = person.get("organization") if isinstance(person.get("organization"), dict) else {}
        return {
            "id": person.get("id"),
            "title": person.get("title"),
            "city": person.get("city"),
            "state": person.get("state"),
            "country": person.get("country") or person.get("person_country"),
            "organization_id": organization.get("id") or person.get("organization_id"),
            "organization_name": organization.get("name") or person.get("organization_name"),
            "organization_domain": organization.get("primary_domain") or person.get("organization_primary_domain"),
            "organization_website_url": organization.get("website_url") or person.get("company_url"),
        }

    def personalize_prospects(self, agent_id: int, *, limit: int = 5) -> SalesPersonalizeResult:
        if limit < 1 or limit > 25:
            raise ValueError("Personalization limit must be between 1 and 25.")
        candidates = list_sales_prospects(agent_id=agent_id, status="imported", limit=limit)
        logger.info("sales_personalization_started", extra={"agent_id": agent_id, "candidate_count": len(candidates)})
        personalized = 0
        eval_failed = 0
        failed = 0
        for prospect in candidates:
            try:
                transition_prospect_status(
                    prospect.id,
                    "personalization_pending",
                    event_message="Personalization started.",
                    event_details={"source": "sales_agent_service"},
                )
                strategy = self.personalization_client.create_strategy(prospect)
                preview_token, preview_record = self.preview_service.create_preview_token(prospect.id)
                unsubscribe_token, _ = self.preview_service.create_unsubscribe_token(prospect.id)
                preview_link = self._join_url(os.getenv("CONTROL_PUBLIC_BASE_URL", ""), f"/v1/sales/preview/{preview_token}")
                unsubscribe_link = self._join_url(
                    os.getenv("SALES_UNSUBSCRIBE_BASE_URL", ""),
                    f"/v1/sales/unsubscribe/{unsubscribe_token}",
                )
                subject, body = build_sales_email(
                    prospect=prospect,
                    strategy=strategy,
                    preview_link=preview_link,
                    unsubscribe_link=unsubscribe_link,
                    booking_link=os.getenv("TEMPA_DEMO_BOOKING_URL", ""),
                    sender_name=os.getenv("SALES_SENDER_NAME", "Max"),
                    postal_address=os.getenv("SALES_POSTAL_ADDRESS", ""),
                )
                personalization = create_personalization(
                    prospect_id=prospect.id,
                    strategy_json=strategy,
                    email_subject=subject,
                    email_body=body,
                )
                eval_result = self.eval_service.evaluate(
                    SalesEvalInput(
                        strategy_json=strategy,
                        email_subject=subject,
                        email_body=body,
                        postal_address=os.getenv("SALES_POSTAL_ADDRESS", "").strip() or None,
                        unsubscribe_link=unsubscribe_link,
                    )
                )
                record_eval_result(
                    prospect_id=prospect.id,
                    personalization_id=personalization.id,
                    status="passed" if eval_result.passed else "failed",
                    deterministic_passed=eval_result.deterministic_passed,
                    llm_passed=eval_result.llm_passed,
                    failures_json=eval_result.failures,
                )
                if not eval_result.passed:
                    logger.info(
                        "sales_eval_failed",
                        extra={"agent_id": agent_id, "prospect_id": prospect.id, "failure_count": len(eval_result.failures)},
                    )
                    transition_prospect_status(
                        prospect.id,
                        "eval_failed",
                        event_message="Personalization failed eval.",
                        event_details={"failures": eval_result.failures},
                    )
                    eval_failed += 1
                    continue
                transition_prospect_status(
                    prospect.id,
                    "ready_to_preview",
                    event_message="Preview draft created.",
                    event_details={"preview_token_id": preview_record.id},
                )
                create_outreach_message(
                    agent_id=agent_id,
                    prospect_id=prospect.id,
                    personalization_id=personalization.id,
                    preview_token_id=preview_record.id,
                    subject=subject,
                    body=body,
                    status="ready_to_send",
                )
                transition_prospect_status(
                    prospect.id,
                    "ready_to_send",
                    event_message="Message passed eval and is ready for capped sending.",
                    event_details={"personalization_id": personalization.id},
                )
                logger.info(
                    "sales_personalization_finished",
                    extra={"agent_id": agent_id, "prospect_id": prospect.id, "status": "ready_to_send"},
                )
                personalized += 1
            except Exception as exc:
                logger.info(
                    "sales_personalization_failed",
                    extra={"agent_id": agent_id, "prospect_id": prospect.id, "error_type": type(exc).__name__},
                )
                try:
                    transition_prospect_status(
                        prospect.id,
                        "personalization_failed",
                        event_message="Personalization failed.",
                        event_details={"error": str(exc)[:240]},
                    )
                except Exception:
                    pass
                failed += 1
        logger.info(
            "sales_personalization_batch_finished",
            extra={"agent_id": agent_id, "personalized": personalized, "eval_failed": eval_failed, "failed": failed},
        )
        return SalesPersonalizeResult(personalized=personalized, eval_failed=eval_failed, failed=failed)

    def list_prospects(self, *, agent_id: int | None = None, status: str | None = None) -> list[dict]:
        return [prospect.model_dump() for prospect in list_sales_prospects(agent_id=agent_id, status=status)]

    def list_messages(self, *, agent_id: int | None = None, status: str | None = None) -> list[dict]:
        return [message.model_dump() for message in list_sales_messages(agent_id=agent_id, status=status)]

    def dry_run_summary(self, agent_id: int, *, limit: int = 25) -> SalesDryRunSummary:
        messages = list_sales_messages(agent_id=agent_id, status="ready_to_send", limit=limit)
        items: list[SalesDryRunSummaryItem] = []
        blocked_count = 0
        for message in messages:
            prospect = get_prospect(message.prospect_id)
            personalization = get_personalization(message.personalization_id) if message.personalization_id else None
            eval_result = get_latest_eval_result(
                prospect_id=message.prospect_id,
                personalization_id=message.personalization_id,
            )
            eval_failures = list(eval_result.failures_json) if eval_result else []
            if eval_result and eval_result.status == "passed" and eval_result.llm_passed is not True:
                eval_failures.append("LLM rubric approval is missing.")
            if not eval_result or eval_result.status != "passed" or eval_failures:
                blocked_count += 1
            prospect_name = None
            if prospect:
                prospect_name = " ".join(part for part in [prospect.first_name, prospect.last_name] if part) or None
            items.append(
                SalesDryRunSummaryItem(
                    message_id=message.id,
                    prospect_id=message.prospect_id,
                    company_name=prospect.company_name if prospect else "Unknown company",
                    prospect_name=prospect_name,
                    prospect_title=prospect.title if prospect else None,
                    company_domain=prospect.company_domain if prospect else None,
                    country=prospect.country if prospect else None,
                    subject=message.subject,
                    email_body=message.body,
                    preview_link=self._extract_preview_link(message.body),
                    eval_status=eval_result.status if eval_result else "missing",
                    eval_failures=eval_failures,
                    passed_reasons=self._passed_reasons(
                        personalization.strategy_json if personalization else None,
                        eval_failures,
                        eval_status=eval_result.status if eval_result else "missing",
                    ),
                )
            )
        return SalesDryRunSummary(
            agent_id=agent_id,
            ready_count=max(0, len(items) - blocked_count),
            blocked_count=blocked_count,
            send_mode=os.getenv("SALES_SEND_MODE", "dry_run"),
            kill_switch=os.getenv("SALES_KILL_SWITCH", "true").lower() != "false",
            first_live_approval_status=(
                "message_scoped"
            ),
            items=items,
        )

    def health(self, agent_id: int | None = None) -> dict[str, Any]:
        if agent_id:
            agent = get_sales_agent(agent_id)
            agents = [agent] if agent else []
        else:
            agents = list_sales_agents(limit=50)
        send_mode = os.getenv("SALES_SEND_MODE", "dry_run")
        return {
            "send_mode": send_mode,
            "kill_switch": os.getenv("SALES_KILL_SWITCH", "true").lower() != "false",
            "agents": [
                {
                    **agent.model_dump(),
                    "first_live_approval_status": "message_scoped",
                    "senders": [
                        {
                            **sender.model_dump(),
                            "health": self.sender_health_service.evaluate_sender(
                                sender,
                                send_mode=send_mode,
                            ).model_dump(),
                        }
                        for sender in list_sender_accounts(agent.id)
                    ],
                }
                for agent in agents
            ],
        }

    def _join_url(self, base_url: str, path: str) -> str:
        base = base_url.strip().rstrip("/")
        if not base:
            return path
        return f"{base}{path}"

    def _extract_preview_link(self, email_body: str) -> str | None:
        for match in re.findall(r"https?://\S+|/v1/sales/preview/\S+", email_body):
            if "/v1/sales/preview/" in match:
                return match.rstrip(".,)")
        return None

    def _passed_reasons(
        self,
        strategy: dict[str, Any] | None,
        eval_failures: list[str],
        *,
        eval_status: str | None,
    ) -> list[str]:
        if eval_status != "passed" or eval_failures:
            return []
        evidence_count = len(strategy.get("evidence_urls", [])) if strategy else 0
        return [
            "Required strategy fields are present.",
            f"{evidence_count} HTTPS evidence URL{'s' if evidence_count != 1 else ''} attached.",
            "Confidence score met the threshold.",
            "Postal address and unsubscribe link are present.",
            "No banned or unsupported numeric claims were found.",
        ]

    def _summarize_companies(self, items: list[SalesDryRunSummaryItem]) -> str:
        companies = [item.company_name for item in items[:5]]
        if not companies:
            return "none"
        suffix = f" and {len(items) - 5} more" if len(items) > 5 else ""
        return ", ".join(companies) + suffix
