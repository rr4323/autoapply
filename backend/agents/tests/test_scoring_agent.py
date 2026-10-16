"""Scoring Agent wiring (docs/BACKEND_BUILD_STEPS.md Step 30): consume
context.retrieved -> publish application.scored + persist score to
applications. Needs Docker (real Postgres) — run via
`make test-integration-py`.
"""

from __future__ import annotations

import asyncio
import json

import asyncpg
import fakeredis
import pytest

from agentos_agents.common.envelope import Envelope, working_memory_key
from agentos_agents.common.llm_client import LLMClient
from agentos_agents.common.topics import TOPIC_APPLICATION_SCORED, TOPIC_CONTEXT_RETRIEVED
from agentos_agents.scoring.agent import ScoringConsumer

pytestmark = pytest.mark.integration

REQUIRED_SKILLS = ["Go experience", "Kubernetes experience"]
CANDIDATE_SKILLS = ["Go", "Python"]
LLM_SCORE = 75

# keyword_overlap: "Go experience" matches candidate skill "Go" (word
# boundary), "Kubernetes experience" matches neither -> ratio = 0.5
# retrieval: top similarities [0.8, 0.0] -> mean 0.4, covered_ratio 0.5
#   (only the first clears the 0.5 default threshold)
#   -> retrieval_component = (0.4 + 0.5) / 2 = 0.45
# semantic: 75 / 100 = 0.75
# total = 0.5*0.3 + 0.45*0.3 + 0.75*0.4 = 0.15 + 0.135 + 0.3 = 0.585 -> round(58.5...) = 59
EXPECTED_SCORE = 59


class FakeLLMClient(LLMClient):
    async def complete(self, system: str, user: str) -> str:
        return json.dumps({"score": LLM_SCORE, "rationale": "solid overlap"})


@pytest.fixture
def redis_client():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


async def seed_application_and_profile(pool: asyncpg.Pool) -> str:
    user_id = await pool.fetchval(
        "INSERT INTO users (email) VALUES ($1) RETURNING id", "scoring-test@example.com"
    )
    await pool.execute(
        "INSERT INTO profiles (user_id, skills, experience_json) "
        "VALUES ($1::uuid, $2, '[]'::jsonb)",
        str(user_id),
        CANDIDATE_SKILLS,
    )
    app_id = await pool.fetchval(
        """
        INSERT INTO applications (user_id, source, role_title, company)
        VALUES ($1::uuid, 'manual', 'Senior Backend Engineer', 'Acme Corp')
        RETURNING id
        """,
        str(user_id),
    )
    return str(app_id)


async def seed_context_retrieved(redis_client: fakeredis.FakeAsyncRedis, job_id: str) -> None:
    jd_key = working_memory_key(job_id, "jd_parsed")
    await redis_client.set(
        jd_key,
        json.dumps(
            {
                "title": "Senior Backend Engineer",
                "company": "Acme Corp",
                "required_skills": REQUIRED_SKILLS,
                "responsibilities": [],
            }
        ),
    )

    context_key = working_memory_key(job_id, "context_retrieved")
    await redis_client.set(
        context_key,
        json.dumps(
            {
                "requirements": [
                    {"requirement": REQUIRED_SKILLS[0], "chunks": [{"similarity": 0.8}]},
                    {"requirement": REQUIRED_SKILLS[1], "chunks": []},
                ],
                "similar_past_applications": [],
            }
        ),
    )

    env = Envelope(
        job_id=job_id,
        trace_id="trace-1",
        event_type=TOPIC_CONTEXT_RETRIEVED,
        produced_by="retriever-agent",
        timestamp="2026-08-10T00:00:00Z",
        payload_ref=context_key,
    )
    await redis_client.xadd(TOPIC_CONTEXT_RETRIEVED, env.model_dump())


async def run_briefly(consumer: ScoringConsumer, seconds: float = 0.5) -> None:
    task = asyncio.create_task(consumer.run())
    await asyncio.sleep(seconds)
    consumer.stop()
    await asyncio.wait_for(task, timeout=2.0)


async def test_scoring_agent_persists_and_publishes_application_scored(pg_pool, redis_client):
    app_id = await seed_application_and_profile(pg_pool)
    await seed_context_retrieved(redis_client, app_id)

    consumer = ScoringConsumer(
        redis_client, pg_pool, "scoring-group", "scoring-1", FakeLLMClient(), block_ms=100
    )
    await run_briefly(consumer)

    entries = await redis_client.xrange(TOPIC_APPLICATION_SCORED)
    assert len(entries) == 1
    _entry_id, fields = entries[0]
    assert fields["job_id"] == app_id
    assert fields["event_type"] == TOPIC_APPLICATION_SCORED
    assert fields["produced_by"] == "scoring-agent"

    payload = json.loads(await redis_client.get(fields["payload_ref"]))
    assert payload["score"] == EXPECTED_SCORE
    assert payload["scoring_model_version"] == "heuristic-v1"
    assert set(payload["signals"].keys()) == {
        "keyword_overlap",
        "retrieval_relevance",
        "llm_semantic",
    }

    row = await pg_pool.fetchrow(
        "SELECT jd_fit_score, resume_match_score, score_breakdown_json, "
        "scoring_model_version, status FROM applications WHERE id = $1::uuid",
        app_id,
    )
    assert row["jd_fit_score"] == EXPECTED_SCORE
    assert row["resume_match_score"] == EXPECTED_SCORE
    assert row["scoring_model_version"] == "heuristic-v1"
    assert row["status"] == "scored"
    persisted_breakdown = json.loads(row["score_breakdown_json"])
    assert persisted_breakdown["score"] == EXPECTED_SCORE

    idempotency_rows = await pg_pool.fetch(
        "SELECT event_type, produced_by_agent FROM application_events "
        "WHERE application_id = $1::uuid",
        app_id,
    )
    assert len(idempotency_rows) == 1
    assert idempotency_rows[0]["event_type"] == TOPIC_APPLICATION_SCORED
    assert idempotency_rows[0]["produced_by_agent"] == "scoring-agent"


async def test_scoring_agent_redelivery_produces_no_duplicate_side_effect(pg_pool, redis_client):
    app_id = await seed_application_and_profile(pg_pool)
    await seed_context_retrieved(redis_client, app_id)

    consumer = ScoringConsumer(
        redis_client, pg_pool, "scoring-group", "scoring-1", FakeLLMClient(), block_ms=100
    )
    await run_briefly(consumer)

    entries = await redis_client.xrange(TOPIC_CONTEXT_RETRIEVED)
    assert len(entries) == 1
    entry_id, fields = entries[0]

    await consumer._process(entry_id, fields)  # simulate an at-least-once redelivery

    entries = await redis_client.xrange(TOPIC_APPLICATION_SCORED)
    assert len(entries) == 1  # not published twice

    rows = await pg_pool.fetch(
        "SELECT id FROM application_events WHERE application_id = $1::uuid AND event_type = $2",
        app_id,
        TOPIC_APPLICATION_SCORED,
    )
    assert len(rows) == 1  # not recorded twice
