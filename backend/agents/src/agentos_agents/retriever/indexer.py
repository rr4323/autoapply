"""Indexing pipeline: profile save -> chunk -> embed -> write profile_chunks
(docs/BACKEND_BUILD_STEPS.md Step 25, TDD.md §6.1).

No pgvector Python package/numpy dependency needed — pgvector accepts its
text input format (`[v1,v2,...]`) cast with `::vector`, verified directly
against a real pgvector-enabled Postgres before relying on it here.
"""

from __future__ import annotations

import asyncpg

from agentos_agents.retriever.chunker import chunk_experience
from agentos_agents.retriever.embedding import EmbeddingClient
from agentos_agents.retriever.pgvector_util import vector_literal


async def index_profile(
    pg_pool: asyncpg.Pool,
    embedding_client: EmbeddingClient,
    user_id: str,
    experience_json: str | bytes,
) -> int:
    """Re-index one user's profile_chunks from their current
    experience_json, returning the number of chunks written.

    Delete-then-insert inside one transaction, not an upsert or a diff
    against what's already indexed — a resume edit can remove an
    experience entry entirely, and there's no stable identity to match
    an old chunk against a new one across an edit anyway (chunk
    boundaries are derived from bullet text, which the edit may have
    changed). A full atomic replace is what "no orphans" (Step 25's own
    done-when criterion) actually requires.
    """
    chunks = chunk_experience(experience_json)
    vectors = await embedding_client.embed_batch([c.text for c in chunks]) if chunks else []

    async with pg_pool.acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM profile_chunks WHERE user_id = $1::uuid", user_id)
        if chunks:
            await conn.executemany(
                """
                INSERT INTO profile_chunks (user_id, source_section, text, embedding)
                VALUES ($1::uuid, $2, $3, $4::vector)
                """,
                [
                    (user_id, chunk.source_section, chunk.text, vector_literal(vector))
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ],
            )

    return len(chunks)
