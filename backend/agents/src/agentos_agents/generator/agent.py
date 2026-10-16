"""Generator Agent wiring — M5 exit (docs/BACKEND_BUILD_STEPS.md Step 38)
plus the cover-letter/screener-answer generation Step 38 deferred and
Step 45's end-to-end run needs for real: consumes policy.decision, acts
only when action == "generate", generates all three document types
(TDD.md §3's full description of this agent) in one handle() call, and
publishes a single documents.generated event carrying everything the
Filler Agent needs to actually fill a form — not three separate events
requiring the Filler to wait on and correlate all of them.
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
from agentos_agents.common.llm_client import LLMClient
from agentos_agents.common.publisher import Publisher
from agentos_agents.common.topics import TOPIC_DOCUMENTS_GENERATED, TOPIC_POLICY_DECISION
from agentos_agents.generator.citation import check_document_groundedness
from agentos_agents.generator.guardrail import GuardrailVerdict, scan_document
from agentos_agents.generator.prompt import (
    SYSTEM_PROMPT,
    RetrievedChunkRef,
    StaticProfileFields,
    build_generation_prompt,
)
from agentos_agents.generator.screener_answers import draft_all_screener_answers
from agentos_agents.generator.storage import ObjectStorageClient
from agentos_agents.scoring.jd_rendering import render_jd_text

logger = logging.getLogger(__name__)

AGENT_NAME = "generator-agent"
WORKING_MEMORY_TTL_SECONDS = 24 * 60 * 60
BUCKET = "generated-documents"

# profiles/users (TDD.md §8) have no first/last-name or phone fields yet —
# a real schema gap flagged since Step 38, not something to fabricate
# realistically. Used as-is for the fields a real profile would supply,
# so the Filler Agent still has something to put in every form field.
PLACEHOLDER_FIRST_NAME = "Demo"
PLACEHOLDER_LAST_NAME = "Candidate"
PLACEHOLDER_PHONE = "555-0100"


class GeneratorConsumer(Consumer):
    def __init__(
        self,
        redis_client: redis.Redis,
        pg_pool: asyncpg.Pool,
        group: str,
        consumer_name: str,
        llm_client: LLMClient,
        storage_client: ObjectStorageClient,
        block_ms: int = 500,
    ) -> None:
        super().__init__(
            redis_client, TOPIC_POLICY_DECISION, group, consumer_name, block_ms=block_ms
        )
        self.pg_pool = pg_pool
        self.llm_client = llm_client
        self.storage_client = storage_client
        self.idempotency = ApplicationEventsIdempotency(
            pg_pool, TOPIC_DOCUMENTS_GENERATED, AGENT_NAME
        )
        self.publisher = Publisher(redis_client)

    async def is_duplicate(self, entry_id: str, fields: dict[str, Any]) -> bool:
        job_id = fields.get("job_id")
        if not job_id:
            return False
        return await self.idempotency.already_handled(job_id)

    async def handle(self, entry_id: str, fields: dict[str, Any]) -> None:
        env = Envelope(**fields)

        raw = await self.redis.get(env.payload_ref)
        decision = json.loads(raw) if raw else {}
        if decision.get("action") != "generate":
            return

        app_row = await self.pg_pool.fetchrow(
            "SELECT user_id FROM applications WHERE id = $1::uuid", env.job_id
        )
        if app_row is None:
            logger.error("no application found for job_id %s", env.job_id)
            return
        user_id = str(app_row["user_id"])

        user_row = await self.pg_pool.fetchrow(
            "SELECT email FROM users WHERE id = $1::uuid", user_id
        )
        user_email = user_row["email"] if user_row else ""

        jd_raw = await self.redis.get(working_memory_key(env.job_id, "jd_parsed"))
        jd = json.loads(jd_raw) if jd_raw else {}
        jd_text = render_jd_text(jd)

        context_raw = await self.redis.get(working_memory_key(env.job_id, "context_retrieved"))
        context = json.loads(context_raw) if context_raw else {}
        chunks = _flatten_chunks(context.get("requirements") or [])

        profile = StaticProfileFields(
            name=f"{PLACEHOLDER_FIRST_NAME} {PLACEHOLDER_LAST_NAME}", email=user_email
        )

        resume = await self._generate_document(
            env.job_id, "resume", jd_text, chunks, profile, user_email
        )
        if resume is None:
            return  # blocked by the guardrail scan — logged there, nothing to publish

        cover_letter = await self._generate_document(
            env.job_id, "cover_letter", jd_text, chunks, profile, user_email
        )
        if cover_letter is None:
            return

        screener_answers = await draft_all_screener_answers(
            self.llm_client, jd.get("screener_questions") or [], chunks, jd_text
        )
        # An answer that fails Step 37's validation is left out of the fill
        # values (the field goes unfilled) rather than blocking the whole
        # application — needs_input as a real pause is Phase H (Step 50),
        # not built yet; this is the honest interim behavior.
        for a in screener_answers:
            if not a.valid:
                logger.warning(
                    "screener answer failed validation, leaving field unfilled",
                    extra={"job_id": env.job_id, "question": a.question, "reason": a.reason},
                )
        screener_storage_ref = await self.storage_client.put(
            BUCKET,
            f"{env.job_id}/screener_answers.json",
            json.dumps([asdict(a) for a in screener_answers]).encode("utf-8"),
            content_type="application/json",
        )
        await self._persist(env.job_id, "screener_answer", screener_storage_ref, [], None)

        wm_key = working_memory_key(env.job_id, "documents_generated")
        payload = {
            "resume": resume,
            "cover_letter": cover_letter,
            "fill_values": {
                "first_name": PLACEHOLDER_FIRST_NAME,
                "last_name": PLACEHOLDER_LAST_NAME,
                "email": user_email,
                "phone": PLACEHOLDER_PHONE,
                "cover_letter": cover_letter["text"],
                **{a.question: a.answer for a in screener_answers if a.valid},
            },
        }
        await self.redis.set(wm_key, json.dumps(payload), ex=WORKING_MEMORY_TTL_SECONDS)
        await self.idempotency.record(env.job_id, payload)

        out_env = Envelope(
            job_id=env.job_id,
            trace_id=env.trace_id,
            event_type=TOPIC_DOCUMENTS_GENERATED,
            produced_by=AGENT_NAME,
            timestamp=utc_timestamp(),
            payload_ref=wm_key,
        )
        await self.publisher.publish(TOPIC_DOCUMENTS_GENERATED, out_env)

    async def _generate_document(
        self,
        job_id: str,
        doc_type: str,
        jd_text: str,
        chunks: list[RetrievedChunkRef],
        profile: StaticProfileFields,
        user_email: str,
    ) -> dict[str, Any] | None:
        section = "resume bullets" if doc_type == "resume" else "cover letter body"
        prompt = build_generation_prompt(jd_text, chunks, profile, section=section)
        generated_text = await self.llm_client.complete(SYSTEM_PROMPT, prompt)

        guardrail = await scan_document(
            generated_text, allowed_emails=[user_email], allowed_urls=[], llm_client=self.llm_client
        )
        if guardrail.verdict == GuardrailVerdict.BLOCK:
            logger.error(
                "generated document blocked by guardrail scan",
                extra={"job_id": job_id, "doc_type": doc_type, "reasons": guardrail.reasons},
            )
            return None

        groundedness = check_document_groundedness(generated_text, chunks)
        source_chunk_ids = sorted({r.chunk_id for r in groundedness.results if r.grounded})
        groundedness_score = (
            len(source_chunk_ids) / len(groundedness.results) if groundedness.results else None
        )

        storage_ref = await self.storage_client.put(
            BUCKET,
            f"{job_id}/{doc_type}.txt",
            generated_text.encode("utf-8"),
            content_type="text/plain",
        )
        document_id = await self._persist(
            job_id, doc_type, storage_ref, source_chunk_ids, groundedness_score
        )

        return {
            "document_id": document_id,
            "type": doc_type,
            "storage_ref": storage_ref,
            "source_chunk_ids": source_chunk_ids,
            "groundedness_score": groundedness_score,
            "text": generated_text,
        }

    async def _persist(
        self,
        application_id: str,
        doc_type: str,
        storage_ref: str,
        source_chunk_ids: list[str],
        groundedness_score: float | None,
    ) -> str:
        row = await self.pg_pool.fetchrow(
            """
            INSERT INTO generated_documents
                (application_id, type, storage_ref, source_chunk_ids, groundedness_score)
            VALUES ($1::uuid, $2, $3, $4::uuid[], $5)
            RETURNING id
            """,
            application_id,
            doc_type,
            storage_ref,
            source_chunk_ids,
            groundedness_score,
        )
        return str(row["id"])


def _flatten_chunks(requirements: list[dict]) -> list[RetrievedChunkRef]:
    # One document draws on all retrieved evidence, not just one
    # requirement's chunks — dedup by chunk_id since the same chunk can
    # legitimately be the top match for more than one requirement.
    by_id: dict[str, RetrievedChunkRef] = {}
    for requirement in requirements:
        for chunk in requirement.get("chunks") or []:
            chunk_id = chunk.get("chunk_id")
            if chunk_id and chunk_id not in by_id:
                by_id[chunk_id] = RetrievedChunkRef(
                    chunk_id=chunk_id,
                    source_section=chunk.get("source_section", ""),
                    text=chunk.get("text", ""),
                )
    return list(by_id.values())
