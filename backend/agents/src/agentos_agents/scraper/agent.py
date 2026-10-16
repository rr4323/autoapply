"""Scraper Agent wiring — M2 exit (docs/BACKEND_BUILD_STEPS.md Step 21).

Consumes jd.discovered, validates + fetches + parses the JD (Steps 18-20),
writes the result to working memory, records the idempotency ledger entry,
and publishes jd.parsed. TDD.md §14.2's URL validation applies here even
though the URL was already headed to a known ATS allowlist by the time it
reaches this agent — this is the boundary that actually enforces it, not
just documents it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any
from urllib.parse import urlparse

import asyncpg
import httpx
import redis.asyncio as redis

from agentos_agents.common.consumer import Consumer
from agentos_agents.common.envelope import Envelope, utc_timestamp, working_memory_key
from agentos_agents.common.idempotency import ApplicationEventsIdempotency
from agentos_agents.common.publisher import Publisher
from agentos_agents.common.topics import TOPIC_JD_DISCOVERED, TOPIC_JD_PARSED
from agentos_agents.scraper.fetcher import FetchError, fetch_jd_html
from agentos_agents.scraper.parser import ParsedJD, UnsupportedATSError, parse_jd
from agentos_agents.scraper.screener import extract_screener_questions
from agentos_agents.scraper.url_validator import (
    Resolver,
    URLValidationError,
    default_resolver,
    validate_url,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "scraper-agent"
WORKING_MEMORY_TTL_SECONDS = 24 * 60 * 60  # matches the Go API's workingMemoryTTL

# Phase 1 scope (per docs/PRD.md) is Greenhouse + Lever — the only two
# platforms parser.py/screener.py know how to read.
DEFAULT_ATS_ALLOWLIST = ["greenhouse.io", "lever.co"]


class ScraperConsumer(Consumer):
    def __init__(
        self,
        redis_client: redis.Redis,
        pg_pool: asyncpg.Pool,
        group: str,
        consumer_name: str,
        http_client: httpx.AsyncClient,
        allowlist: list[str] | None = None,
        resolver: Resolver = default_resolver,
        block_ms: int = 500,
        allow_insecure_local_targets: bool = False,
    ) -> None:
        super().__init__(redis_client, TOPIC_JD_DISCOVERED, group, consumer_name, block_ms=block_ms)
        self.pg_pool = pg_pool
        self.idempotency = ApplicationEventsIdempotency(pg_pool, TOPIC_JD_PARSED, AGENT_NAME)
        self.publisher = Publisher(redis_client)
        self.http_client = http_client
        self.allowlist = allowlist or DEFAULT_ATS_ALLOWLIST
        self.resolver = resolver
        self.allow_insecure_local_targets = allow_insecure_local_targets

    async def is_duplicate(self, entry_id: str, fields: dict[str, Any]) -> bool:
        job_id = fields.get("job_id")
        if not job_id:
            return False
        return await self.idempotency.already_handled(job_id)

    async def handle(self, entry_id: str, fields: dict[str, Any]) -> None:
        env = Envelope(**fields)

        raw = await self.redis.get(env.payload_ref)
        source = json.loads(raw) if raw else {}
        jd_url = source.get("jd_url")
        jd_text = source.get("jd_text")

        payload = await self._parse(jd_url, jd_text)
        await self._persist_metadata(env.job_id, payload)

        wm_key = working_memory_key(env.job_id, "jd_parsed")
        await self.redis.set(wm_key, json.dumps(payload), ex=WORKING_MEMORY_TTL_SECONDS)

        await self.idempotency.record(env.job_id, payload)

        out_env = Envelope(
            job_id=env.job_id,
            trace_id=env.trace_id,
            event_type=TOPIC_JD_PARSED,
            produced_by=AGENT_NAME,
            timestamp=utc_timestamp(),
            payload_ref=wm_key,
        )
        await self.publisher.publish(TOPIC_JD_PARSED, out_env)

    async def _persist_metadata(self, application_id: str, payload: dict[str, Any]) -> None:
        """Writes the parsed title/company back onto applications (raw SQL,
        same as scoring/persistence.py — sqlc is Go-only). Nothing else in
        the pipeline does this, so without it the API's ApplicationSummary
        (company/role_title) stays null forever even though parse_jd
        extracted real values — a gap the frontend's list/detail views
        made obvious.

        Best-effort: only overwrites a field when the parse actually
        produced a non-empty value, so a parse failure's _empty_payload
        (title=None, company=None) never clobbers a value a previous
        successful parse already wrote (e.g. on redelivery after a
        transient fetch error).
        """
        title = payload.get("title")
        company = payload.get("company")
        if not title and not company:
            return
        await self.pg_pool.execute(
            """
            UPDATE applications
            SET company = COALESCE($1, company),
                role_title = COALESCE($2, role_title),
                updated_at = now()
            WHERE id = $3::uuid
            """,
            company,
            title,
            application_id,
        )

    async def _parse(self, jd_url: str | None, jd_text: str | None) -> dict[str, Any]:
        if jd_url:
            return await self._parse_from_url(jd_url)
        return _empty_payload(raw_text=jd_text)

    async def _parse_from_url(self, jd_url: str) -> dict[str, Any]:
        try:
            validate_url(
                jd_url,
                self.allowlist,
                resolver=self.resolver,
                allow_insecure_local_targets=self.allow_insecure_local_targets,
            )
            hostname = urlparse(jd_url).hostname or ""
            html = await fetch_jd_html(jd_url, self.http_client)
            parsed = parse_jd(html, hostname)
            questions = extract_screener_questions(html, hostname)
        except (URLValidationError, FetchError, UnsupportedATSError) as e:
            # No dead-letter/retry infrastructure exists yet (out of scope
            # for this step) — logged loudly and the failure recorded in
            # working memory instead, so the pipeline doesn't silently
            # stall and whoever reads the jd_parsed stage next can see why.
            logger.error("failed to parse JD from %r: %s", jd_url, e)
            return _empty_payload(error=str(e))

        payload = asdict(parsed)
        payload["screener_questions"] = [
            {"question": q.question, "field_type": q.field_type.value, "options": q.options}
            for q in questions
        ]
        return payload


def _empty_payload(raw_text: str | None = None, error: str | None = None) -> dict[str, Any]:
    payload = asdict(ParsedJD())
    payload["screener_questions"] = []
    if raw_text is not None:
        payload["raw_text"] = raw_text
    if error is not None:
        payload["error"] = error
    return payload
