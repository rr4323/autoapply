"""Filler+Verifier Agent wiring (docs/BACKEND_BUILD_STEPS.md Step 45):
consumes documents.generated (seeded directly, matching every other
agent's test convention of seeding its own upstream stage rather than
running the previous agent) -> fills the real Step 39 fixture -> verifies
-> publishes application.terminal. The same required edge case as
Step 43's test_verifier.py, now driven through the full consumer wiring
with the Generator's actual output shape (fill_values keyed by question
text for screener fields, matching what GeneratorConsumer produces).
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx
from conftest import VALUES

from agentos_agents.common.envelope import Envelope, working_memory_key
from agentos_agents.common.llm_client import LLMClient
from agentos_agents.common.topics import TOPIC_APPLICATION_TERMINAL, TOPIC_DOCUMENTS_GENERATED
from agentos_agents.filler.agent import FillerVerifierConsumer
from agentos_agents.filler.verify import PolicyCallbackClient

pytestmark = pytest.mark.integration

POLICY_BASE_URL = "http://policy-engine.internal:8080"
CALLBACK_URL = f"{POLICY_BASE_URL}/internal/agent/callback"

FULL_FIELD_MAP = {
    "first_name": "#first_name",
    "last_name": "#last_name",
    "email": "#email",
    "phone": "#phone",
    "cover_letter": "#cover_letter",
    "Why are you interested in this role?": "#q_why",
    "How many years of experience do you have with Go?": "#q_years",
    "Are you legally authorized to work in the country of this job?": "#q_auth",
}

FILL_VALUES = {
    "first_name": "Demo",
    "last_name": "Candidate",
    "email": "filler-verifier-test@example.com",
    "phone": "555-0100",
    "cover_letter": VALUES["cover_letter"],
    "Why are you interested in this role?": VALUES["q_why"],
    "How many years of experience do you have with Go?": VALUES["q_years"],
    "Are you legally authorized to work in the country of this job?": VALUES["q_auth"],
}


class FakeFullDomAnalysisLLMClient(LLMClient):
    def __init__(self) -> None:
        self.call_count = 0

    async def complete(self, system: str, user: str) -> str:
        self.call_count += 1
        return json.dumps(FULL_FIELD_MAP)


def _mock_policy_engine() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["bot_check_detected"]:
            return httpx.Response(
                409,
                json={
                    "accepted": False,
                    "action": "require_review",
                    "reasons": ["bot-check detected"],
                },
            )
        return httpx.Response(
            200, json={"accepted": True, "action": "submit", "reasons": ["clean pass"]}
        )

    respx.post(CALLBACK_URL).mock(side_effect=responder)


async def seed_application_with_jd_url(pool, jd_url: str) -> str:
    user_id = await pool.fetchval(
        "INSERT INTO users (email) VALUES ($1) RETURNING id", FILL_VALUES["email"]
    )
    app_id = await pool.fetchval(
        """
        INSERT INTO applications (user_id, source, jd_url, role_title, company)
        VALUES ($1::uuid, 'manual', $2, 'Senior Backend Engineer', 'Acme Corp')
        RETURNING id
        """,
        str(user_id),
        jd_url,
    )
    return str(app_id)


async def seed_documents_generated(redis_client, job_id: str) -> None:
    wm_key = working_memory_key(job_id, "documents_generated")
    await redis_client.set(wm_key, json.dumps({"fill_values": FILL_VALUES}))

    env = Envelope(
        job_id=job_id,
        trace_id="trace-1",
        event_type=TOPIC_DOCUMENTS_GENERATED,
        produced_by="generator-agent",
        timestamp="2026-08-10T00:00:00Z",
        payload_ref=wm_key,
    )
    await redis_client.xadd(TOPIC_DOCUMENTS_GENERATED, env.model_dump())


async def run_briefly(consumer: FillerVerifierConsumer, seconds: float = 0.5) -> None:
    task = asyncio.create_task(consumer.run())
    await asyncio.sleep(seconds)
    consumer.stop()
    await asyncio.wait_for(task, timeout=2.0)


@respx.mock
async def test_clean_fixture_end_to_end_results_in_submitted(
    pg_pool, redis_client, browser, ats_fixtures_url
):
    _mock_policy_engine()
    jd_url = f"{ats_fixtures_url}/clean/"
    app_id = await seed_application_with_jd_url(pg_pool, jd_url)
    await seed_documents_generated(redis_client, app_id)

    dom_llm = FakeFullDomAnalysisLLMClient()
    async with httpx.AsyncClient() as http_client:
        policy_client = PolicyCallbackClient(http_client, POLICY_BASE_URL, "s3cret")
        consumer = FillerVerifierConsumer(
            redis_client, pg_pool, "filler-group", "filler-1",
            browser, dom_llm, policy_client, block_ms=100,
        )
        await run_briefly(consumer)

    entries = await redis_client.xrange(TOPIC_APPLICATION_TERMINAL)
    assert len(entries) == 1
    _entry_id, fields = entries[0]
    payload = json.loads(await redis_client.get(fields["payload_ref"]))
    assert payload["status"] == "submitted"
    assert payload["bot_check_detected"] is False


@respx.mock
async def test_captcha_fixture_end_to_end_results_in_ready_for_review(
    pg_pool, redis_client, browser, ats_fixtures_url
):
    _mock_policy_engine()
    jd_url = f"{ats_fixtures_url}/captcha/"
    app_id = await seed_application_with_jd_url(pg_pool, jd_url)
    await seed_documents_generated(redis_client, app_id)

    dom_llm = FakeFullDomAnalysisLLMClient()
    async with httpx.AsyncClient() as http_client:
        policy_client = PolicyCallbackClient(http_client, POLICY_BASE_URL, "s3cret")
        consumer = FillerVerifierConsumer(
            redis_client, pg_pool, "filler-group", "filler-1",
            browser, dom_llm, policy_client, block_ms=100,
        )
        await run_briefly(consumer)

    entries = await redis_client.xrange(TOPIC_APPLICATION_TERMINAL)
    assert len(entries) == 1
    _entry_id, fields = entries[0]
    payload = json.loads(await redis_client.get(fields["payload_ref"]))
    assert payload["status"] == "ready_for_review"
    assert payload["bot_check_detected"] is True
