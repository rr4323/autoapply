"""M3 exit — Retriever Agent wiring (docs/BACKEND_BUILD_STEPS.md Step 26).

The plan's own done-when criterion: "a known (requirement -> expected
chunk) pair ranks the expected chunk first" against seeded pgvector data.
Uses a small deterministic bag-of-words fake embedding client (not the
all-zero one from test_indexer.py) specifically so two chunks are
genuinely distinguishable by cosine similarity — proving the SQL ranking
itself, independent of real embedding-model quality (out of scope here).
"""

from __future__ import annotations

import asyncio
import json

import asyncpg
import fakeredis
import pytest

from agentos_agents.common.envelope import Envelope, working_memory_key
from agentos_agents.common.topics import TOPIC_CONTEXT_RETRIEVED, TOPIC_JD_PARSED
from agentos_agents.retriever.agent import RetrieverConsumer
from agentos_agents.retriever.embedding import EmbeddingClient
from agentos_agents.retriever.indexer import index_profile

pytestmark = pytest.mark.integration

VOCAB = ["go", "backend", "distributed", "marketing", "campaigns"]

RELEVANT_BULLET = "Built backend services in Go with distributed systems design"
IRRELEVANT_BULLET = "Led marketing campaigns for consumer products"
REQUIREMENT = "Go backend experience"


class FakeKeywordEmbeddingClient(EmbeddingClient):
    """Bag-of-words over a tiny fixed vocabulary — genuinely different
    vectors for genuinely different text, deterministic, no network call.
    """

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            words = set(text.lower().replace(",", " ").replace(".", " ").split())
            vec = [1.0 if term in words else 0.0 for term in VOCAB]
            vec += [0.0] * (1536 - len(VOCAB))
            vectors.append(vec)
        return vectors


@pytest.fixture
def redis_client():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


async def seed_application_with_profile(pool: asyncpg.Pool, embedder: EmbeddingClient) -> str:
    user_id = await pool.fetchval(
        "INSERT INTO users (email) VALUES ($1) RETURNING id", "retriever-test@example.com"
    )
    app_id = await pool.fetchval(
        """
        INSERT INTO applications (user_id, source, role_title, company)
        VALUES ($1::uuid, 'manual', 'Senior Backend Engineer', 'Acme Corp')
        RETURNING id
        """,
        str(user_id),
    )

    experience = json.dumps(
        [
            {
                "id": "e1",
                "company": "Old Co",
                "title": "Backend Engineer",
                "start_date": "2018-01",
                "end_date": "2020-01",
                "bullets": [RELEVANT_BULLET, IRRELEVANT_BULLET],
            }
        ]
    )
    await index_profile(pool, embedder, str(user_id), experience)
    return str(app_id)


async def seed_jd_parsed(redis_client: fakeredis.FakeAsyncRedis, job_id: str) -> None:
    wm_key = working_memory_key(job_id, "jd_parsed")
    await redis_client.set(
        wm_key,
        json.dumps(
            {
                "title": "Senior Backend Engineer",
                "company": "Acme Corp",
                "required_skills": [REQUIREMENT],
                "responsibilities": [],
                "screener_questions": [],
            }
        ),
    )
    env = Envelope(
        job_id=job_id,
        trace_id="trace-1",
        event_type=TOPIC_JD_PARSED,
        produced_by="scraper-agent",
        timestamp="2026-08-10T00:00:00Z",
        payload_ref=wm_key,
    )
    await redis_client.xadd(TOPIC_JD_PARSED, env.model_dump())


async def run_briefly(consumer: RetrieverConsumer, seconds: float = 0.5) -> None:
    task = asyncio.create_task(consumer.run())
    await asyncio.sleep(seconds)
    consumer.stop()
    await asyncio.wait_for(task, timeout=2.0)


async def test_retriever_agent_ranks_expected_chunk_first(pg_pool, redis_client):
    embedder = FakeKeywordEmbeddingClient()
    app_id = await seed_application_with_profile(pg_pool, embedder)
    await seed_jd_parsed(redis_client, app_id)

    consumer = RetrieverConsumer(
        redis_client, pg_pool, "retriever-group", "retriever-1", embedder, block_ms=100
    )
    await run_briefly(consumer)

    entries = await redis_client.xrange(TOPIC_CONTEXT_RETRIEVED)
    assert len(entries) == 1
    _entry_id, fields = entries[0]
    assert fields["job_id"] == app_id
    assert fields["event_type"] == TOPIC_CONTEXT_RETRIEVED
    assert fields["produced_by"] == "retriever-agent"

    payload = json.loads(await redis_client.get(fields["payload_ref"]))
    assert len(payload["requirements"]) == 1
    requirement_result = payload["requirements"][0]
    assert requirement_result["requirement"] == REQUIREMENT

    chunks = requirement_result["chunks"]
    assert len(chunks) == 2
    assert chunks[0]["text"] == RELEVANT_BULLET
    assert chunks[1]["text"] == IRRELEVANT_BULLET
    assert chunks[0]["similarity"] > chunks[1]["similarity"]
    assert chunks[0]["similarity"] > 0
    assert chunks[1]["similarity"] == 0  # orthogonal bag-of-words vectors

    rows = await pg_pool.fetch(
        "SELECT event_type, produced_by_agent FROM application_events "
        "WHERE application_id = $1::uuid",
        app_id,
    )
    assert len(rows) == 1
    assert rows[0]["event_type"] == TOPIC_CONTEXT_RETRIEVED
    assert rows[0]["produced_by_agent"] == "retriever-agent"


async def test_retriever_agent_redelivery_produces_no_duplicate_side_effect(pg_pool, redis_client):
    embedder = FakeKeywordEmbeddingClient()
    app_id = await seed_application_with_profile(pg_pool, embedder)
    await seed_jd_parsed(redis_client, app_id)

    consumer = RetrieverConsumer(
        redis_client, pg_pool, "retriever-group", "retriever-1", embedder, block_ms=100
    )
    await run_briefly(consumer)

    entries = await redis_client.xrange(TOPIC_JD_PARSED)
    assert len(entries) == 1
    entry_id, fields = entries[0]

    await consumer._process(entry_id, fields)  # simulate an at-least-once redelivery

    entries = await redis_client.xrange(TOPIC_CONTEXT_RETRIEVED)
    assert len(entries) == 1  # not published twice

    rows = await pg_pool.fetch(
        "SELECT id FROM application_events WHERE application_id = $1::uuid AND event_type = $2",
        app_id,
        TOPIC_CONTEXT_RETRIEVED,
    )
    assert len(rows) == 1  # not recorded twice
