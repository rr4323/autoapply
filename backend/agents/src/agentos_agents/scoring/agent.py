"""Scoring Agent wiring (docs/BACKEND_BUILD_STEPS.md Step 30). Consumes
context.retrieved, runs all three signals (Steps 27-28), combines them
(Step 29), persists the result to applications, writes working memory,
and publishes application.scored.

Reads *two* working-memory records for one job, not just this message's
own payload_ref: jd_parsed (Step 21's output — title/company/
required_skills/responsibilities, still live under its own key) for the
keyword-overlap signal and the semantic-signal JD text, and
context_retrieved (this message's payload) for the pre-computed retrieval
stats. This is working memory used as TDD.md §5 actually describes it —
a per-job scratchpad every agent can read from, not a single-hop handoff
that only carries the most recent stage's data forward.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg
import redis.asyncio as redis

from agentos_agents.common.consumer import Consumer
from agentos_agents.common.envelope import Envelope, utc_timestamp, working_memory_key
from agentos_agents.common.idempotency import ApplicationEventsIdempotency
from agentos_agents.common.llm_client import LLMClient
from agentos_agents.common.publisher import Publisher
from agentos_agents.common.topics import TOPIC_APPLICATION_SCORED, TOPIC_CONTEXT_RETRIEVED
from agentos_agents.scoring.combiner import combine_scores
from agentos_agents.scoring.jd_rendering import render_jd_text
from agentos_agents.scoring.persistence import persist_score
from agentos_agents.scoring.semantic_signal import llm_semantic_score
from agentos_agents.scoring.signals import keyword_skills_overlap, retrieval_relevance_stats

logger = logging.getLogger(__name__)

AGENT_NAME = "scoring-agent"
WORKING_MEMORY_TTL_SECONDS = 24 * 60 * 60


class ScoringConsumer(Consumer):
    def __init__(
        self,
        redis_client: redis.Redis,
        pg_pool: asyncpg.Pool,
        group: str,
        consumer_name: str,
        llm_client: LLMClient,
        block_ms: int = 500,
    ) -> None:
        super().__init__(
            redis_client, TOPIC_CONTEXT_RETRIEVED, group, consumer_name, block_ms=block_ms
        )
        self.pg_pool = pg_pool
        self.llm_client = llm_client
        self.idempotency = ApplicationEventsIdempotency(
            pg_pool, TOPIC_APPLICATION_SCORED, AGENT_NAME
        )
        self.publisher = Publisher(redis_client)

    async def is_duplicate(self, entry_id: str, fields: dict[str, Any]) -> bool:
        job_id = fields.get("job_id")
        if not job_id:
            return False
        return await self.idempotency.already_handled(job_id)

    async def handle(self, entry_id: str, fields: dict[str, Any]) -> None:
        env = Envelope(**fields)

        app_row = await self.pg_pool.fetchrow(
            "SELECT user_id FROM applications WHERE id = $1::uuid", env.job_id
        )
        if app_row is None:
            logger.error("no application found for job_id %s", env.job_id)
            return
        user_id = str(app_row["user_id"])

        profile_row = await self.pg_pool.fetchrow(
            "SELECT skills FROM profiles WHERE user_id = $1::uuid", user_id
        )
        candidate_skills: list[str] = list(profile_row["skills"]) if profile_row else []

        jd_raw = await self.redis.get(working_memory_key(env.job_id, "jd_parsed"))
        jd = json.loads(jd_raw) if jd_raw else {}
        required_skills: list[str] = jd.get("required_skills") or []

        context_raw = await self.redis.get(env.payload_ref)
        context = json.loads(context_raw) if context_raw else {}
        requirements: list[dict] = context.get("requirements") or []

        keyword_result = keyword_skills_overlap(required_skills, candidate_skills)
        retrieval_stats = retrieval_relevance_stats(requirements)

        jd_text = render_jd_text(jd)
        candidate_summary = ", ".join(candidate_skills) or "(no skills listed)"
        semantic_result = await llm_semantic_score(self.llm_client, jd_text, candidate_summary)

        breakdown = combine_scores(keyword_result, retrieval_stats, semantic_result)

        await persist_score(self.pg_pool, env.job_id, breakdown)

        wm_key = working_memory_key(env.job_id, "application_scored")
        payload = breakdown.to_json_dict()
        await self.redis.set(wm_key, json.dumps(payload), ex=WORKING_MEMORY_TTL_SECONDS)
        await self.idempotency.record(env.job_id, payload)

        out_env = Envelope(
            job_id=env.job_id,
            trace_id=env.trace_id,
            event_type=TOPIC_APPLICATION_SCORED,
            produced_by=AGENT_NAME,
            timestamp=utc_timestamp(),
            payload_ref=wm_key,
        )
        await self.publisher.publish(TOPIC_APPLICATION_SCORED, out_env)
