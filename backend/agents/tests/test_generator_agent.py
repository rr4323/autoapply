"""M5 exit — Generator Agent wiring (docs/BACKEND_BUILD_STEPS.md Step 38),
now producing all three document types (resume, cover_letter,
screener_answer — Step 45's extension).

Done-when: "source_chunk_ids non-empty and all resolvable" — verified
directly against real Postgres (every id in source_chunk_ids must be a
real profile_chunks row) and a real MinIO container (the storage_ref
must actually round-trip the generated text, not just be a fabricated
string).
"""

from __future__ import annotations

import asyncio
import json

import asyncpg
import fakeredis
import pytest
from testcontainers.community.minio import MinioContainer

from agentos_agents.common.envelope import Envelope, working_memory_key
from agentos_agents.common.llm_client import LLMClient
from agentos_agents.common.topics import TOPIC_DOCUMENTS_GENERATED, TOPIC_POLICY_DECISION
from agentos_agents.generator.agent import GeneratorConsumer
from agentos_agents.generator.storage import MinioStorageClient
from agentos_agents.retriever.embedding import EmbeddingClient
from agentos_agents.retriever.indexer import index_profile

pytestmark = pytest.mark.integration

RELEVANT_BULLET = "Led the backend platform team using Go and PostgreSQL"
GENERATED_RESUME_TEMPLATE = "{bullet}.[chunk:{chunk_id}]"


class ZeroEmbeddingClient(EmbeddingClient):
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]


class FakeGeneratorLLMClient(LLMClient):
    def __init__(self, generated_text: str) -> None:
        self.generated_text = generated_text
        self.call_count = 0

    async def complete(self, system: str, user: str) -> str:
        self.call_count += 1
        return self.generated_text


@pytest.fixture
def redis_client():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def minio_client():
    with MinioContainer() as container:
        yield container.get_client()


async def seed_application_with_profile(pool: asyncpg.Pool) -> tuple[str, str]:
    user_id = await pool.fetchval(
        "INSERT INTO users (email) VALUES ($1) RETURNING id", "generator-test@example.com"
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
                "company": "Acme Corp",
                "title": "Senior Backend Engineer",
                "start_date": "2020-01",
                "end_date": None,
                "bullets": [RELEVANT_BULLET],
            }
        ]
    )
    await index_profile(pool, ZeroEmbeddingClient(), str(user_id), experience)

    chunk_row = await pool.fetchrow(
        "SELECT id FROM profile_chunks WHERE user_id = $1::uuid LIMIT 1", str(user_id)
    )
    return str(app_id), str(chunk_row["id"])


async def seed_working_memory_for_generation(
    redis_client: fakeredis.FakeAsyncRedis, job_id: str, chunk_id: str
) -> None:
    await redis_client.set(
        working_memory_key(job_id, "jd_parsed"),
        json.dumps(
            {
                "title": "Senior Backend Engineer",
                "company": "Acme Corp",
                "required_skills": ["Go backend experience"],
                "responsibilities": [],
            }
        ),
    )

    policy_decision_key = working_memory_key(job_id, "context_retrieved")
    await redis_client.set(
        policy_decision_key,
        json.dumps(
            {
                "requirements": [
                    {
                        "requirement": "Go backend experience",
                        "chunks": [
                            {
                                "chunk_id": chunk_id,
                                "source_section": "Senior Backend Engineer @ Acme Corp",
                                "text": RELEVANT_BULLET,
                                "similarity": 0.9,
                            }
                        ],
                    }
                ],
                "similar_past_applications": [],
            }
        ),
    )

    decision_key = working_memory_key(job_id, "policy_decision")
    await redis_client.set(
        decision_key,
        json.dumps(
            {
                "decision_point": "post_scoring",
                "action": "generate",
                "reasons": ["score cleared min_generate_score"],
                "rules_version": "policy-rules-v1",
            }
        ),
    )
    env = Envelope(
        job_id=job_id,
        trace_id="trace-1",
        event_type=TOPIC_POLICY_DECISION,
        produced_by="policy-engine",
        timestamp="2026-08-10T00:00:00Z",
        payload_ref=decision_key,
    )
    await redis_client.xadd(TOPIC_POLICY_DECISION, env.model_dump())


async def run_briefly(consumer: GeneratorConsumer, seconds: float = 0.5) -> None:
    task = asyncio.create_task(consumer.run())
    await asyncio.sleep(seconds)
    consumer.stop()
    await asyncio.wait_for(task, timeout=2.0)


async def test_generator_agent_produces_resolvable_source_chunk_ids(
    pg_pool, redis_client, minio_client
):
    app_id, chunk_id = await seed_application_with_profile(pg_pool)
    await seed_working_memory_for_generation(redis_client, app_id, chunk_id)

    generated_text = GENERATED_RESUME_TEMPLATE.format(bullet=RELEVANT_BULLET, chunk_id=chunk_id)
    llm = FakeGeneratorLLMClient(generated_text)
    storage = MinioStorageClient(minio_client)

    consumer = GeneratorConsumer(
        redis_client, pg_pool, "generator-group", "generator-1", llm, storage, block_ms=100
    )
    await run_briefly(consumer)

    entries = await redis_client.xrange(TOPIC_DOCUMENTS_GENERATED)
    assert len(entries) == 1
    _entry_id, fields = entries[0]
    assert fields["job_id"] == app_id
    assert fields["produced_by"] == "generator-agent"

    payload = json.loads(await redis_client.get(fields["payload_ref"]))
    assert payload["resume"]["source_chunk_ids"] == [chunk_id]
    assert payload["cover_letter"]["source_chunk_ids"] == [chunk_id]
    assert payload["fill_values"]["cover_letter"] == generated_text
    assert payload["fill_values"]["email"] == "generator-test@example.com"

    # persisted rows — all three document types
    rows = await pg_pool.fetch(
        "SELECT type, storage_ref, source_chunk_ids, groundedness_score "
        "FROM generated_documents WHERE application_id = $1::uuid ORDER BY type",
        app_id,
    )
    assert {r["type"] for r in rows} == {"cover_letter", "resume", "screener_answer"}

    resume_row = next(r for r in rows if r["type"] == "resume")
    persisted_chunk_ids = [str(v) for v in resume_row["source_chunk_ids"]]
    assert persisted_chunk_ids == [chunk_id]
    assert resume_row["groundedness_score"] == 1.0

    # "all resolvable" — every cited chunk_id is a real profile_chunks row
    resolvable = await pg_pool.fetch(
        "SELECT id FROM profile_chunks WHERE id = ANY($1::uuid[])", persisted_chunk_ids
    )
    assert len(resolvable) == len(persisted_chunk_ids)

    # the resume storage_ref actually round-trips through MinIO
    bucket, key = resume_row["storage_ref"].split("/", 1)
    obj = minio_client.get_object(bucket, key)
    try:
        assert obj.read().decode("utf-8") == generated_text
    finally:
        obj.close()

    events = await pg_pool.fetch(
        "SELECT event_type, produced_by_agent FROM application_events "
        "WHERE application_id = $1::uuid",
        app_id,
    )
    assert len(events) == 1
    assert events[0]["event_type"] == TOPIC_DOCUMENTS_GENERATED
    assert events[0]["produced_by_agent"] == "generator-agent"


async def test_generator_agent_ignores_non_generate_decisions(pg_pool, redis_client, minio_client):
    app_id, chunk_id = await seed_application_with_profile(pg_pool)

    await redis_client.set(
        working_memory_key(app_id, "jd_parsed"), json.dumps({"required_skills": []})
    )
    decision_key = working_memory_key(app_id, "policy_decision")
    await redis_client.set(
        decision_key,
        json.dumps(
            {"decision_point": "post_scoring", "action": "stop", "reasons": ["below threshold"]}
        ),
    )
    env = Envelope(
        job_id=app_id,
        trace_id="trace-1",
        event_type=TOPIC_POLICY_DECISION,
        produced_by="policy-engine",
        timestamp="2026-08-10T00:00:00Z",
        payload_ref=decision_key,
    )
    await redis_client.xadd(TOPIC_POLICY_DECISION, env.model_dump())

    llm = FakeGeneratorLLMClient("should never be called")
    storage = MinioStorageClient(minio_client)
    consumer = GeneratorConsumer(
        redis_client, pg_pool, "generator-group", "generator-1", llm, storage, block_ms=100
    )
    await run_briefly(consumer)

    assert llm.call_count == 0
    entries = await redis_client.xrange(TOPIC_DOCUMENTS_GENERATED)
    assert entries == []
