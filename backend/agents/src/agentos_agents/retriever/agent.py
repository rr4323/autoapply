"""Retriever Agent wiring — M3 exit (docs/BACKEND_BUILD_STEPS.md Step 26,
TDD.md §6.2). Consumes jd.parsed, embeds each required-skill requirement
snippet, queries profile_chunks for the top-k most similar chunks per
requirement plus a similar-past-applications lookup, writes the result to
working memory, and publishes context.retrieved — not silently discarded
after use, per §6.2's own wording.

"Requirement snippets" is scoped to required_skills specifically, not
responsibilities — responsibilities describe the role, required_skills
describe what's asked of the candidate, and it's the candidate's own
profile facts (via profile_chunks) being matched against.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

import asyncpg
import redis.asyncio as redis

from agentos_agents.common.consumer import Consumer
from agentos_agents.common.envelope import Envelope, utc_timestamp, working_memory_key
from agentos_agents.common.idempotency import ApplicationEventsIdempotency
from agentos_agents.common.publisher import Publisher
from agentos_agents.common.topics import TOPIC_CONTEXT_RETRIEVED, TOPIC_JD_PARSED
from agentos_agents.retriever.embedding import EmbeddingClient
from agentos_agents.retriever.retrieval import (
    find_similar_past_applications,
    top_k_chunks_for_requirement,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "retriever-agent"
WORKING_MEMORY_TTL_SECONDS = 24 * 60 * 60
DEFAULT_TOP_K = 5


class RetrieverConsumer(Consumer):
    def __init__(
        self,
        redis_client: redis.Redis,
        pg_pool: asyncpg.Pool,
        group: str,
        consumer_name: str,
        embedding_client: EmbeddingClient,
        top_k: int = DEFAULT_TOP_K,
        block_ms: int = 500,
    ) -> None:
        super().__init__(redis_client, TOPIC_JD_PARSED, group, consumer_name, block_ms=block_ms)
        self.pg_pool = pg_pool
        self.embedding_client = embedding_client
        self.top_k = top_k
        self.idempotency = ApplicationEventsIdempotency(
            pg_pool, TOPIC_CONTEXT_RETRIEVED, AGENT_NAME
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
            "SELECT user_id, role_title, company FROM applications WHERE id = $1::uuid", env.job_id
        )
        if app_row is None:
            # jd.parsed referencing an application that doesn't exist would
            # be a real upstream bug — nothing this agent can recover from,
            # so it's logged loudly and the message is still acked (no
            # dead-letter queue exists yet to route it to instead).
            logger.error("no application found for job_id %s", env.job_id)
            return
        user_id = str(app_row["user_id"])

        raw = await self.redis.get(env.payload_ref)
        jd = json.loads(raw) if raw else {}
        requirements: list[str] = jd.get("required_skills") or []

        per_requirement = []
        for requirement in requirements:
            chunks = await top_k_chunks_for_requirement(
                self.pg_pool, self.embedding_client, user_id, requirement, k=self.top_k
            )
            per_requirement.append(
                {"requirement": requirement, "chunks": [asdict(c) for c in chunks]}
            )

        role_title = jd.get("title") or app_row["role_title"]
        similar_apps = await find_similar_past_applications(
            self.pg_pool, user_id, role_title, env.job_id
        )

        payload = {
            "requirements": per_requirement,
            "similar_past_applications": [asdict(a) for a in similar_apps],
        }

        wm_key = working_memory_key(env.job_id, "context_retrieved")
        await self.redis.set(wm_key, json.dumps(payload), ex=WORKING_MEMORY_TTL_SECONDS)
        await self.idempotency.record(env.job_id, payload)

        out_env = Envelope(
            job_id=env.job_id,
            trace_id=env.trace_id,
            event_type=TOPIC_CONTEXT_RETRIEVED,
            produced_by=AGENT_NAME,
            timestamp=utc_timestamp(),
            payload_ref=wm_key,
        )
        await self.publisher.publish(TOPIC_CONTEXT_RETRIEVED, out_env)
