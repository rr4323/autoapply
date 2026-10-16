"""Retrieval (TDD.md §6.2): top-k profile_chunks per JD requirement snippet
(semantic memory), plus a similar-past-applications lookup (episodic
memory) for score-calibration context.

The episodic side has no spec'd algorithm anywhere in TDD.md/PRD.md beyond
one line ("a secondary query ... for similar past applications") and
applications carry no embedding of their own to do a real vector search
against — so this is a deliberately simple word-overlap heuristic on
role_title, not a claim of semantic matching. Flagged here the same way
the Step 15 contract-shape gaps were: honest about what this actually
does, not silently underbuilt.
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from agentos_agents.retriever.embedding import EmbeddingClient
from agentos_agents.retriever.pgvector_util import vector_literal

_STOPWORDS = {"a", "an", "the", "of", "for", "and", "at", "in", "on", "to"}


@dataclass
class RetrievedChunk:
    chunk_id: str
    source_section: str
    text: str
    similarity: float


@dataclass
class SimilarApplication:
    application_id: str
    role_title: str | None
    company: str | None
    resume_match_score: float | None
    jd_fit_score: float | None
    outcome: str | None


async def top_k_chunks_for_requirement(
    pg_pool: asyncpg.Pool,
    embedding_client: EmbeddingClient,
    user_id: str,
    requirement: str,
    k: int = 5,
) -> list[RetrievedChunk]:
    vectors = await embedding_client.embed_batch([requirement])
    if not vectors:
        return []
    query_vector = vector_literal(vectors[0])

    # pgvector's <=> is cosine *distance* (0 = identical, 2 = opposite);
    # similarity is the more intuitive number to carry downstream (into
    # the score breakdown a user eventually sees), so it's converted here
    # rather than passing distance through and making every caller invert it.
    rows = await pg_pool.fetch(
        """
        SELECT id, source_section, text, 1 - (embedding <=> $2::vector) AS similarity
        FROM profile_chunks
        WHERE user_id = $1::uuid
        ORDER BY embedding <=> $2::vector
        LIMIT $3
        """,
        user_id,
        query_vector,
        k,
    )
    return [
        RetrievedChunk(
            chunk_id=str(row["id"]),
            source_section=row["source_section"],
            text=row["text"],
            similarity=float(row["similarity"]),
        )
        for row in rows
    ]


async def find_similar_past_applications(
    pg_pool: asyncpg.Pool,
    user_id: str,
    role_title: str | None,
    exclude_application_id: str,
    limit: int = 3,
) -> list[SimilarApplication]:
    if not role_title:
        return []

    rows = await pg_pool.fetch(
        """
        SELECT a.id, a.role_title, a.company, a.resume_match_score, a.jd_fit_score, o.outcome
        FROM applications a
        LEFT JOIN application_outcomes o ON o.application_id = a.id
        WHERE a.user_id = $1::uuid AND a.id != $2::uuid AND a.role_title IS NOT NULL
        """,
        user_id,
        exclude_application_id,
    )
    candidates = [
        SimilarApplication(
            application_id=str(row["id"]),
            role_title=row["role_title"],
            company=row["company"],
            resume_match_score=row["resume_match_score"],
            jd_fit_score=row["jd_fit_score"],
            outcome=row["outcome"],
        )
        for row in rows
    ]
    return _rank_by_title_overlap(role_title, candidates)[:limit]


def _rank_by_title_overlap(
    target_title: str, candidates: list[SimilarApplication]
) -> list[SimilarApplication]:
    target_words = _significant_words(target_title)
    scored = [
        (len(target_words & _significant_words(c.role_title or "")), c) for c in candidates
    ]
    scored = [pair for pair in scored if pair[0] > 0]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [candidate for _, candidate in scored]


def _significant_words(title: str) -> set[str]:
    return {w for w in title.lower().split() if w not in _STOPWORDS}
