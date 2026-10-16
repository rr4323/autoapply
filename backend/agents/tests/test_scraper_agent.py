"""M2 exit — Scraper Agent wiring (docs/BACKEND_BUILD_STEPS.md Step 21).

Needs Docker (a real Postgres testcontainer — application_events is the
idempotency ledger TDD.md §4.2 describes, so this proves the real check,
not a mocked one) — run via `make test-integration-py`, not the default
`make test-py`. Redis is faked (fakeredis), same as every other consumer
test in this suite; the genuinely new integration surface this step adds
is the Postgres side, not the Redis side, which Step 6/7 already proved.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import asyncpg
import fakeredis
import httpx
import pytest
import respx

from agentos_agents.common.envelope import Envelope, working_memory_key
from agentos_agents.common.topics import TOPIC_JD_DISCOVERED, TOPIC_JD_PARSED
from agentos_agents.scraper.agent import ScraperConsumer

pytestmark = pytest.mark.integration

JD_URL = "https://boards.greenhouse.io/example/jobs/1"
FIXTURE_HTML = (Path(__file__).parent / "fixtures" / "greenhouse_job.html").read_text()


def fake_resolver(_hostname: str) -> list[str]:
    return ["93.184.216.34"]  # a real, public, non-private IP — no DNS needed in tests


@pytest.fixture
def redis_client():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


async def seed_application(pool: asyncpg.Pool) -> str:
    user_id = await pool.fetchval(
        "INSERT INTO users (email) VALUES ($1) RETURNING id", "scraper-test@example.com"
    )
    app_id = await pool.fetchval(
        "INSERT INTO applications (user_id, jd_url, source) VALUES ($1, $2, 'manual') RETURNING id",
        user_id,
        JD_URL,
    )
    return str(app_id)


async def seed_jd_discovered(redis_client: fakeredis.FakeAsyncRedis, job_id: str) -> None:
    wm_key = working_memory_key(job_id, "jd_discovered")
    await redis_client.set(wm_key, json.dumps({"jd_url": JD_URL, "jd_text": None}))
    env = Envelope(
        job_id=job_id,
        trace_id="trace-1",
        event_type=TOPIC_JD_DISCOVERED,
        produced_by="api",
        timestamp="2026-08-10T00:00:00Z",
        payload_ref=wm_key,
    )
    await redis_client.xadd(TOPIC_JD_DISCOVERED, env.model_dump())


async def run_briefly(consumer: ScraperConsumer, seconds: float = 0.5) -> None:
    task = asyncio.create_task(consumer.run())
    await asyncio.sleep(seconds)
    consumer.stop()
    await asyncio.wait_for(task, timeout=2.0)


@respx.mock
async def test_scraper_agent_publishes_jd_parsed_and_records_idempotency(pg_pool, redis_client):
    respx.get(JD_URL).mock(
        return_value=httpx.Response(200, headers={"content-type": "text/html"}, text=FIXTURE_HTML)
    )

    app_id = await seed_application(pg_pool)
    await seed_jd_discovered(redis_client, app_id)

    async with httpx.AsyncClient() as http_client:
        consumer = ScraperConsumer(
            redis_client,
            pg_pool,
            "scraper-group",
            "scraper-1",
            http_client,
            resolver=fake_resolver,
            block_ms=100,
        )
        await run_briefly(consumer)

    entries = await redis_client.xrange(TOPIC_JD_PARSED)
    assert len(entries) == 1
    _entry_id, fields = entries[0]
    assert fields["job_id"] == app_id
    assert fields["event_type"] == TOPIC_JD_PARSED
    assert fields["produced_by"] == "scraper-agent"

    payload = json.loads(await redis_client.get(fields["payload_ref"]))
    assert payload["title"] == "Senior Backend Engineer"
    assert payload["company"] == "Acme Corp"
    assert len(payload["screener_questions"]) == 3
    assert {
        "question": "Are you legally authorized to work in the country of this job?",
        "field_type": "yes_no",
        "options": ["Yes", "No"],
    } in payload["screener_questions"]

    rows = await pg_pool.fetch(
        "SELECT event_type, produced_by_agent FROM application_events "
        "WHERE application_id = $1::uuid",
        app_id,
    )
    assert len(rows) == 1
    assert rows[0]["event_type"] == TOPIC_JD_PARSED
    assert rows[0]["produced_by_agent"] == "scraper-agent"

    app_row = await pg_pool.fetchrow(
        "SELECT company, role_title FROM applications WHERE id = $1::uuid", app_id
    )
    assert app_row["company"] == "Acme Corp"
    assert app_row["role_title"] == "Senior Backend Engineer"


@respx.mock
async def test_scraper_agent_redelivery_produces_no_duplicate_side_effect(pg_pool, redis_client):
    """Redis Streams gives at-least-once delivery (TDD.md §4.1) — a message
    already fully processed and acked can still be redelivered (e.g. a
    consumer that processed it but crashed before the ack reached Redis).
    Reprocessing that exact message must be a no-op per §4.2. Simulated
    directly via a second _process() call with the original entry, since
    forcing Redis itself to redeliver an already-acked entry isn't
    something the protocol supports — the mechanics of *how* a duplicate
    delivery can happen are already covered by test_consumer.py's
    test_redelivery_path; this test is specifically about what happens
    when one does.
    """
    respx.get(JD_URL).mock(
        return_value=httpx.Response(200, headers={"content-type": "text/html"}, text=FIXTURE_HTML)
    )

    app_id = await seed_application(pg_pool)
    await seed_jd_discovered(redis_client, app_id)

    async with httpx.AsyncClient() as http_client:
        consumer = ScraperConsumer(
            redis_client,
            pg_pool,
            "scraper-group",
            "scraper-1",
            http_client,
            resolver=fake_resolver,
            block_ms=100,
        )
        await run_briefly(consumer)

        entries = await redis_client.xrange(TOPIC_JD_DISCOVERED)
        assert len(entries) == 1
        entry_id, fields = entries[0]

        # Redeliver the identical message a second time.
        await consumer._process(entry_id, fields)

    entries = await redis_client.xrange(TOPIC_JD_PARSED)
    assert len(entries) == 1  # not published twice

    rows = await pg_pool.fetch(
        "SELECT id FROM application_events WHERE application_id = $1::uuid AND event_type = $2",
        app_id,
        TOPIC_JD_PARSED,
    )
    assert len(rows) == 1  # not recorded twice
