"""Filler+Verifier Agent wiring — Step 45's end-to-end run (docs/BACKEND_BUILD_STEPS.md).
Consumes documents.generated, opens the application's jd_url in a fresh
ephemeral browser context (§14.3, Step 41), fills it from the Generator's
output (falling back to LLM-assisted DOM analysis if no cached selector
map exists), runs the Verifier's detect -> ask -> submit sequence
(Step 43), and publishes application.terminal.

One consumer, not two, even though Filler and Verifier are two rows in
TDD.md's architecture table — see filler/verify.py's module docstring
for why a live Playwright page can't cross the message-bus boundary
between them. form.filled is still published as its own event, between
the fill and the verify steps, for observability/audit.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

import asyncpg
import redis.asyncio as redis
from playwright.async_api import Browser

from agentos_agents.common.consumer import Consumer
from agentos_agents.common.envelope import Envelope, utc_timestamp, working_memory_key
from agentos_agents.common.idempotency import ApplicationEventsIdempotency
from agentos_agents.common.llm_client import LLMClient
from agentos_agents.common.publisher import Publisher
from agentos_agents.common.topics import TOPIC_DOCUMENTS_GENERATED, TOPIC_FORM_FILLED
from agentos_agents.filler.browser import ephemeral_context
from agentos_agents.filler.fill import fill_form
from agentos_agents.filler.procedural_memory import ProceduralMemoryRepo
from agentos_agents.filler.verify import (
    PolicyCallbackClient,
    publish_terminal_event,
    verify_and_submit,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "filler-agent"
WORKING_MEMORY_TTL_SECONDS = 24 * 60 * 60


class FillerVerifierConsumer(Consumer):
    def __init__(
        self,
        redis_client: redis.Redis,
        pg_pool: asyncpg.Pool,
        group: str,
        consumer_name: str,
        browser: Browser,
        dom_analysis_llm: LLMClient,
        policy_client: PolicyCallbackClient,
        block_ms: int = 500,
    ) -> None:
        super().__init__(
            redis_client, TOPIC_DOCUMENTS_GENERATED, group, consumer_name, block_ms=block_ms
        )
        self.pg_pool = pg_pool
        self.browser = browser
        self.dom_analysis_llm = dom_analysis_llm
        self.policy_client = policy_client
        self.idempotency = ApplicationEventsIdempotency(pg_pool, TOPIC_FORM_FILLED, AGENT_NAME)
        self.publisher = Publisher(redis_client)

    async def is_duplicate(self, entry_id: str, fields: dict[str, Any]) -> bool:
        job_id = fields.get("job_id")
        if not job_id:
            return False
        return await self.idempotency.already_handled(job_id)

    async def handle(self, entry_id: str, fields: dict[str, Any]) -> None:
        env = Envelope(**fields)

        raw = await self.redis.get(env.payload_ref)
        generated = json.loads(raw) if raw else {}
        fill_values: dict[str, str] = generated.get("fill_values") or {}

        app_row = await self.pg_pool.fetchrow(
            "SELECT jd_url FROM applications WHERE id = $1::uuid", env.job_id
        )
        target_url = app_row["jd_url"] if app_row else None
        if not target_url:
            logger.error("no jd_url on application %s, nothing to fill", env.job_id)
            return
        domain = urlparse(target_url).hostname or ""

        procedural_memory = ProceduralMemoryRepo(self.pg_pool)

        async with ephemeral_context(self.browser, domain) as context:
            page = await context.new_page()
            await page.goto(target_url)

            fill_result = await fill_form(
                page, domain, fill_values, procedural_memory, self.dom_analysis_llm
            )
            await self._publish_form_filled(env, fill_result.filled_fields, fill_result.used_cache)

            verify_result = await verify_and_submit(page, env.job_id, domain, self.policy_client)

        await publish_terminal_event(
            self.publisher, self.redis, env.job_id, env.trace_id, verify_result
        )
        await self.idempotency.record(env.job_id, {"outcome": verify_result.outcome})

    async def _publish_form_filled(
        self, env: Envelope, filled_fields: dict[str, str], used_cache: bool
    ) -> None:
        wm_key = working_memory_key(env.job_id, "form_filled")
        await self.redis.set(
            wm_key,
            json.dumps({"filled_fields": list(filled_fields.keys()), "used_cache": used_cache}),
            ex=WORKING_MEMORY_TTL_SECONDS,
        )
        out_env = Envelope(
            job_id=env.job_id,
            trace_id=env.trace_id,
            event_type=TOPIC_FORM_FILLED,
            produced_by=AGENT_NAME,
            timestamp=utc_timestamp(),
            payload_ref=wm_key,
        )
        await self.publisher.publish(TOPIC_FORM_FILLED, out_env)
