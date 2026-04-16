"""Dedicated worker loop for capped sales sending."""

from __future__ import annotations

import os
import logging
import time
from pydantic import BaseModel

from models.sales import (
    claim_next_ready_message,
    count_sender_sent_today,
    get_latest_eval_result,
    get_sales_agent,
    get_prospect,
    is_suppressed,
    list_sales_messages,
    list_sender_accounts,
    mark_claimed_message_status,
    mark_message_sent,
    pause_sender_account,
    record_send_event,
    release_claimed_message,
    transition_prospect_status,
)
from services.agentmail_service import AgentMailSendRequest, AgentMailService
from services.approval_service import external_approval_is_approved
from services.sales_approval_keys import sales_message_approval_event_id
from services.sales_sender_health import SalesSenderHealthService


logger = logging.getLogger(__name__)


class SalesWorkerResult(BaseModel):
    action: str
    message: str
    sent: int = 0


class SalesWorkerLoopResult(BaseModel):
    action: str
    message: str
    passes: int
    sent: int = 0
    last_result: SalesWorkerResult | None = None


class SalesSendWorker:
    def __init__(
        self,
        *,
        agentmail: AgentMailService | None = None,
        health_service: SalesSenderHealthService | None = None,
    ) -> None:
        self.agentmail = agentmail or AgentMailService()
        self.health_service = health_service or SalesSenderHealthService()

    def run_once(self, agent_id: int) -> SalesWorkerResult:
        logger.info("sales_worker_pass_started", extra={"agent_id": agent_id})
        if os.getenv("SALES_AGENT_ENABLED", "false").lower() != "true":
            logger.info("sales_worker_disabled", extra={"agent_id": agent_id})
            return SalesWorkerResult(action="disabled", message="SALES_AGENT_ENABLED is false.")
        if os.getenv("SALES_KILL_SWITCH", "true").lower() != "false":
            logger.info("sales_worker_blocked", extra={"agent_id": agent_id, "reason": "kill_switch"})
            return SalesWorkerResult(action="blocked", message="SALES_KILL_SWITCH is enabled.")

        agent = get_sales_agent(agent_id)
        if not agent:
            return SalesWorkerResult(action="blocked", message=f"Sales agent {agent_id} was not found.")
        if agent.status != "active":
            return SalesWorkerResult(action="blocked", message="Sales agent is paused.")

        env_send_mode = os.getenv("SALES_SEND_MODE", "dry_run")
        if env_send_mode == "live" and agent.send_mode != "live":
            return SalesWorkerResult(action="blocked", message="Sales agent is not configured for live sending.")
        send_mode = "live" if env_send_mode == "live" and agent.send_mode == "live" else "dry_run"
        senders = list_sender_accounts(agent_id, status="active")
        if not senders:
            logger.info("sales_worker_blocked", extra={"agent_id": agent_id, "reason": "no_active_senders"})
            return SalesWorkerResult(action="blocked", message="No active sender accounts.")
        healthy_senders = []
        for sender in senders:
            health = self.health_service.evaluate_sender(sender, send_mode=send_mode)
            if health.pause_reason:
                continue
            healthy_senders.append(sender)
        if not healthy_senders:
            logger.info("sales_worker_blocked", extra={"agent_id": agent_id, "reason": "no_healthy_senders"})
            return SalesWorkerResult(action="blocked", message="No healthy active sender accounts.")
        sent = 0
        for _ in range(10):
            sender = None
            message = None
            for candidate_sender in healthy_senders:
                message = claim_next_ready_message(
                    agent_id=agent_id,
                    sender_account_id=candidate_sender.id,
                    sender_daily_cap=candidate_sender.daily_cap,
                )
                if message:
                    sender = candidate_sender
                    break
            if not message or not sender:
                ready_messages = list_sales_messages(agent_id=agent_id, status="ready_to_send", limit=1)
                if sent:
                    break
                if ready_messages:
                    return SalesWorkerResult(action="capped", message="Daily sender cap reached.", sent=sent)
                logger.info("sales_worker_idle", extra={"agent_id": agent_id})
                return SalesWorkerResult(action="idle", message="No ready messages.")

            live_block = self._live_send_block_reason(send_mode, sender.verified, agent_id=agent_id, message=message)
            if live_block:
                release_claimed_message(message.id)
                logger.info("sales_worker_blocked", extra={"agent_id": agent_id, "reason": "live_send_guard", "sent": sent})
                return SalesWorkerResult(action="blocked", message=live_block, sent=sent)
            prospect = get_prospect(message.prospect_id)
            if not prospect:
                mark_claimed_message_status(message.id, "skipped")
                logger.info("sales_worker_blocked", extra={"agent_id": agent_id, "reason": "missing_prospect", "sent": sent})
                return SalesWorkerResult(action="blocked", message="Message prospect was not found.", sent=sent)
            if is_suppressed(email=prospect.email, domain=prospect.company_domain):
                transition_prospect_status(
                    prospect.id,
                    "suppressed",
                    event_message="Suppressed prospect skipped before send.",
                    event_details={"worker": "sales_send_worker"},
                )
                mark_claimed_message_status(message.id, "skipped")
                logger.info(
                    "sales_worker_skipped_suppressed",
                    extra={"agent_id": agent_id, "prospect_id": prospect.id, "message_id": message.id},
                )
                continue
            if send_mode == "dry_run":
                recorded = record_send_event(
                    event_id=f"dry-run-{message.id}",
                    event_type="message.dry_run",
                    prospect_id=message.prospect_id,
                    sender_account_id=sender.id,
                    safe_metadata_json={"message_id": message.id},
                )
                release_claimed_message(message.id, clear_sender=True)
                if recorded:
                    sent += 1
                logger.info(
                    "sales_worker_dry_run_recorded",
                    extra={"agent_id": agent_id, "prospect_id": prospect.id, "message_id": message.id, "sent": sent},
                )
                continue
            eval_result = get_latest_eval_result(
                prospect_id=message.prospect_id,
                personalization_id=message.personalization_id,
            )
            if not eval_result or eval_result.status != "passed" or eval_result.llm_passed is not True:
                release_claimed_message(message.id)
                return SalesWorkerResult(
                    action="blocked",
                    message="Live send requires a passed eval with LLM rubric approval.",
                    sent=sent,
                )
            if is_suppressed(email=prospect.email, domain=prospect.company_domain):
                transition_prospect_status(
                    prospect.id,
                    "suppressed",
                    event_message="Suppressed prospect skipped immediately before send.",
                    event_details={"worker": "sales_send_worker"},
                )
                mark_claimed_message_status(message.id, "skipped")
                continue
            try:
                result = self.agentmail.send_message(
                    AgentMailSendRequest(
                        inbox_id=sender.inbox_id,
                        to=prospect.email,
                        subject=message.subject,
                        text=message.body,
                    )
                )
            except Exception as exc:
                pause_sender_account(sender.id, "AgentMail rejected a send.")
                release_claimed_message(message.id)
                logger.info(
                    "sales_worker_sender_paused",
                    extra={
                        "agent_id": agent_id,
                        "sender_account_id": sender.id,
                        "message_id": message.id,
                        "error_type": type(exc).__name__,
                    },
                )
                return SalesWorkerResult(action="paused", message=f"Sender paused after send failure: {exc}", sent=sent)
            marked = mark_message_sent(message.id, result.message_id, sender.id)
            if not marked:
                return SalesWorkerResult(action="blocked", message="Message claim was lost before marking sent.", sent=sent)
            transition_prospect_status(
                message.prospect_id,
                "sent",
                event_message="Sales message sent.",
                event_details={"provider": "agentmail"},
            )
            record_send_event(
                event_id=f"send-{result.message_id}",
                event_type="message.sent",
                agentmail_message_id=result.message_id,
                prospect_id=message.prospect_id,
                sender_account_id=sender.id,
                safe_metadata_json={"thread_id": result.thread_id},
            )
            sent += 1
            logger.info(
                "sales_worker_send_recorded",
                extra={"agent_id": agent_id, "prospect_id": prospect.id, "message_id": message.id, "sent": sent},
            )
        logger.info("sales_worker_pass_finished", extra={"agent_id": agent_id, "sent": sent})
        return SalesWorkerResult(action="sent", message="Worker pass completed.", sent=sent)

    def run_loop(
        self,
        agent_id: int,
        *,
        poll_interval_seconds: int = 60,
        max_passes: int | None = None,
        stop_on_blocked: bool = False,
        sleep_fn=time.sleep,
    ) -> SalesWorkerLoopResult:
        poll_interval_seconds = max(1, poll_interval_seconds)
        passes = 0
        total_sent = 0
        last_result: SalesWorkerResult | None = None

        while max_passes is None or passes < max_passes:
            last_result = self.run_once(agent_id)
            passes += 1
            total_sent += last_result.sent

            if last_result.action == "disabled":
                return SalesWorkerLoopResult(
                    action="disabled",
                    message=last_result.message,
                    passes=passes,
                    sent=total_sent,
                    last_result=last_result,
                )
            if stop_on_blocked and last_result.action in {"blocked", "paused"}:
                return SalesWorkerLoopResult(
                    action=last_result.action,
                    message=last_result.message,
                    passes=passes,
                    sent=total_sent,
                    last_result=last_result,
                )
            if max_passes is not None and passes >= max_passes:
                break

            sleep_fn(poll_interval_seconds)

        return SalesWorkerLoopResult(
            action="completed",
            message="Sales worker loop completed.",
            passes=passes,
            sent=total_sent,
            last_result=last_result,
        )

    def _live_send_block_reason(
        self,
        send_mode: str,
        sender_verified: bool,
        *,
        agent_id: int,
        message=None,
    ) -> str | None:
        if send_mode != "live":
            return None
        if not message:
            return "Live send requires an exact reviewed message approval."
        approval_event_id = sales_message_approval_event_id(
            agent_id=agent_id,
            message_id=message.id,
            subject=message.subject,
            body=message.body,
        )
        if not external_approval_is_approved(approval_event_id):
            return "This exact live sales message has not been approved in Slack."
        if not sender_verified:
            return "Sender account is not verified."
        if not os.getenv("AGENTMAIL_SENDER_DOMAIN", "").strip():
            return "AGENTMAIL_SENDER_DOMAIN is not configured."
        if not os.getenv("SALES_POSTAL_ADDRESS", "").strip():
            return "SALES_POSTAL_ADDRESS is not configured."
        if not os.getenv("SALES_UNSUBSCRIBE_BASE_URL", "").strip():
            return "SALES_UNSUBSCRIBE_BASE_URL is not configured."
        return None
