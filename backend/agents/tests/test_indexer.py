"""Indexing pipeline (docs/BACKEND_BUILD_STEPS.md Step 25): profile save ->
chunk -> embed -> write profile_chunks, re-index replaces cleanly.

Needs Docker (real Postgres, pgvector extension) — see conftest.py's
pg_pool fixture, run via `make test-integration-py`.
"""

from __future__ import annotations

import json

import asyncpg
import pytest

from agentos_agents.retriever.embedding import EmbeddingClient
from agentos_agents.retriever.indexer import index_profile

pytestmark = pytest.mark.integration

EXPERIENCE_V1 = [
    {
        "id": "e1",
        "company": "Acme Corp",
        "title": "Senior Backend Engineer",
        "start_date": "2020-01",
        "end_date": None,
        "bullets": ["Led the platform team", "Owned the on-call rotation"],
    }
]

EXPERIENCE_V2 = [
    {
        "id": "e1",
        "company": "Acme Corp",
        "title": "Staff Backend Engineer",
        "start_date": "2020-01",
        "end_date": None,
        "bullets": ["Promoted to staff engineer"],
    }
]


class FakeEmbeddingClient(EmbeddingClient):
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]


async def seed_user(pool: asyncpg.Pool) -> str:
    user_id = await pool.fetchval(
        "INSERT INTO users (email) VALUES ($1) RETURNING id", "indexer-test@example.com"
    )
    return str(user_id)


async def chunk_rows(pool: asyncpg.Pool, user_id: str) -> list[asyncpg.Record]:
    return await pool.fetch(
        "SELECT source_section, text FROM profile_chunks WHERE user_id = $1::uuid ORDER BY text",
        user_id,
    )


async def test_index_profile_writes_one_chunk_per_bullet(pg_pool):
    user_id = await seed_user(pg_pool)
    embedder = FakeEmbeddingClient()

    count = await index_profile(pg_pool, embedder, user_id, json.dumps(EXPERIENCE_V1))

    assert count == 2
    rows = await chunk_rows(pg_pool, user_id)
    assert [r["text"] for r in rows] == ["Led the platform team", "Owned the on-call rotation"]
    assert all(r["source_section"] == "Senior Backend Engineer @ Acme Corp" for r in rows)


async def test_index_profile_resave_replaces_cleanly_no_orphans(pg_pool):
    user_id = await seed_user(pg_pool)
    embedder = FakeEmbeddingClient()

    await index_profile(pg_pool, embedder, user_id, json.dumps(EXPERIENCE_V1))
    count = await index_profile(pg_pool, embedder, user_id, json.dumps(EXPERIENCE_V2))

    assert count == 1
    rows = await chunk_rows(pg_pool, user_id)
    # Only the new version's chunk is present — nothing from V1 survived.
    assert [r["text"] for r in rows] == ["Promoted to staff engineer"]
    assert rows[0]["source_section"] == "Staff Backend Engineer @ Acme Corp"


async def test_index_profile_empty_experience_clears_existing_chunks(pg_pool):
    user_id = await seed_user(pg_pool)
    embedder = FakeEmbeddingClient()

    await index_profile(pg_pool, embedder, user_id, json.dumps(EXPERIENCE_V1))
    count = await index_profile(pg_pool, embedder, user_id, json.dumps([]))

    assert count == 0
    rows = await chunk_rows(pg_pool, user_id)
    assert rows == []


async def test_index_profile_scopes_delete_to_the_indexed_user_only(pg_pool):
    user_a = await seed_user(pg_pool)
    user_b = await pg_pool.fetchval(
        "INSERT INTO users (email) VALUES ($1) RETURNING id", "other-user@example.com"
    )
    embedder = FakeEmbeddingClient()

    await index_profile(pg_pool, embedder, user_a, json.dumps(EXPERIENCE_V1))
    await index_profile(pg_pool, embedder, str(user_b), json.dumps(EXPERIENCE_V1))

    # Re-indexing user A must not touch user B's chunks.
    await index_profile(pg_pool, embedder, user_a, json.dumps([]))

    assert await chunk_rows(pg_pool, user_a) == []
    assert len(await chunk_rows(pg_pool, str(user_b))) == 2
