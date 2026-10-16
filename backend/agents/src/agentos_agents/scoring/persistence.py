"""Persists a ScoreBreakdown to applications (TDD.md §8) — raw SQL from
Python, same as common/idempotency.py, since sqlc's generated Go code
isn't importable from this side of the language boundary.
"""

from __future__ import annotations

import json

import asyncpg

from agentos_agents.scoring.combiner import ScoreBreakdown


async def persist_score(
    pg_pool: asyncpg.Pool, application_id: str, breakdown: ScoreBreakdown
) -> None:
    # jd_fit_score and resume_match_score both get the same combined value
    # — TDD.md distinguishes the two conceptually but specifies no
    # separate formula for either, and there's no data yet to derive one
    # from (the same cold-start gap the fixed heuristic itself exists to
    # cover, TDD.md §16). Documented here rather than silently conflating
    # them without comment.
    await pg_pool.execute(
        """
        UPDATE applications
        SET jd_fit_score = $1,
            resume_match_score = $1,
            score_breakdown_json = $2::jsonb,
            scoring_model_version = $3,
            status = 'scored',
            updated_at = now()
        WHERE id = $4::uuid
        """,
        float(breakdown.score),
        json.dumps(breakdown.to_json_dict()),
        breakdown.scoring_model_version,
        application_id,
    )
