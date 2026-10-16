"""Verifier Agent core logic (docs/BACKEND_BUILD_STEPS.md Step 43,
TDD.md §3/§7.2): detect bot-check on the live, already-filled page
(Step 42), ask the Go control plane's enforcement boundary
(POST /internal/agent/callback, Step 33's §7.3 gate) for a final go/no-go
— never a locally-computed decision, since that boundary exists
specifically so no agent can talk its way past the gate — and either
click submit or leave the application for review.

Filler and Verifier are two agents in TDD.md's architecture table, but a
Playwright browser context can't be handed across a message-bus boundary
— only the process that opened it holds the live page. In practice
they're one continuous browser session run by one worker, publishing
form.filled and application.terminal for observability/audit at each
stage rather than as a literal cross-process handoff.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
import redis.asyncio as redis
from playwright.async_api import Page

from agentos_agents.common.envelope import Envelope, utc_timestamp, working_memory_key
from agentos_agents.common.publisher import Publisher
from agentos_agents.common.topics import TOPIC_APPLICATION_TERMINAL
from agentos_agents.filler.bot_check import detect_bot_check

AGENT_NAME = "verifier-agent"
DEFAULT_SUBMIT_SELECTOR = "#submit_app"
WORKING_MEMORY_TTL_SECONDS = 24 * 60 * 60


@dataclass
class VerificationResult:
    outcome: str  # "submitted" | "ready_for_review"
    reasons: list[str]
    bot_check_detected: bool


class PolicyCallbackError(Exception):
    """Raised when the /internal/agent/callback request itself fails
    (not to be confused with a rejected — but successfully answered —
    submit claim, which is a normal, expected response, not an error).
    """


class PolicyCallbackClient:
    """HTTP client for the Go control plane's §7.3 enforcement boundary."""

    def __init__(self, http_client: httpx.AsyncClient, base_url: str, internal_secret: str) -> None:
        self.http_client = http_client
        self.base_url = base_url
        self.internal_secret = internal_secret

    async def request_submit(self, job_id: str, bot_check_detected: bool) -> tuple[bool, list[str]]:
        try:
            response = await self.http_client.post(
                f"{self.base_url}/internal/agent/callback",
                headers={"X-Internal-Secret": self.internal_secret},
                json={
                    "job_id": job_id,
                    "action": "submit",
                    "bot_check_detected": bot_check_detected,
                },
            )
        except httpx.RequestError as e:
            raise PolicyCallbackError(f"request to agent callback failed: {e}") from e

        # 200 (accepted) and 409 (Go's re-check disagreed) are both
        # normal, successful responses to parse — only a genuine failure
        # to get an answer at all is an error condition here.
        if response.status_code not in (200, 409):
            raise PolicyCallbackError(f"unexpected status {response.status_code}: {response.text}")

        data = response.json()
        return bool(data["accepted"]), list(data.get("reasons", []))


async def verify_and_submit(
    page: Page,
    job_id: str,
    ats_domain: str,
    policy_client: PolicyCallbackClient,
    submit_selector: str = DEFAULT_SUBMIT_SELECTOR,
) -> VerificationResult:
    html = await page.content()
    detection = detect_bot_check(html, page.url, ats_domain)

    accepted, reasons = await policy_client.request_submit(job_id, detection.detected)

    if accepted:
        await page.click(submit_selector)
        outcome = "submitted"
    else:
        outcome = "ready_for_review"

    return VerificationResult(
        outcome=outcome, reasons=reasons, bot_check_detected=detection.detected
    )


async def publish_terminal_event(
    publisher: Publisher,
    redis_client: redis.Redis,
    job_id: str,
    trace_id: str,
    result: VerificationResult,
) -> None:
    wm_key = working_memory_key(job_id, "application_terminal")
    payload = {
        "status": result.outcome,
        "reasons": result.reasons,
        "bot_check_detected": result.bot_check_detected,
    }
    await redis_client.set(wm_key, json.dumps(payload), ex=WORKING_MEMORY_TTL_SECONDS)

    env = Envelope(
        job_id=job_id,
        trace_id=trace_id,
        event_type=TOPIC_APPLICATION_TERMINAL,
        produced_by=AGENT_NAME,
        timestamp=utc_timestamp(),
        payload_ref=wm_key,
    )
    await publisher.publish(TOPIC_APPLICATION_TERMINAL, env)
